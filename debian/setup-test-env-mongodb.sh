#!/bin/bash
set -e

function clean_exit(){
    local error_code="$?"
    rm -rf "$1"
    kill $(jobs -p)
    return $error_code
}

check_for_cmd () {
    if ! which "$1" >/dev/null 2>&1
    then
        echo "Could not find $1 command" 1>&2
        exit 1
    fi
}

wait_for_line () {
    while read line
    do
        echo "$line" | grep -q "$1" && break
    done < "$2"
    # Read the fifo for ever otherwise process would block
    cat "$2" >/dev/null &
}

if [ "$1" = "--coverage" ]; then
	COVERAGE_ARG="$1"
	shift
fi

export PATH=${PATH:+$PATH:}/sbin:/usr/sbin
check_for_cmd mongod

# Start MongoDB process for tests
MONGO_DATA=`mktemp -d /tmp/CEILO-MONGODB-XXXXX`
MONGO_PORT=27017
trap "clean_exit ${MONGO_DATA}" EXIT
mkfifo ${MONGO_DATA}/out
mongod --maxConns 32 --nojournal --noprealloc --smallfiles --quiet --noauth --port ${MONGO_PORT} --dbpath "${MONGO_DATA}" --bind_ip localhost --config /dev/null &>${MONGO_DATA}/out &
# Wait for Mongo to start listening to connections
wait_for_line "waiting for connections on port ${MONGO_PORT}" ${MONGO_DATA}/out
# Read the fifo for ever otherwise mongod would block
cat ${MONGO_DATA}/out > /dev/null &
# It'd be nice if Zaqar understood something like this:
#export CEILOMETER_TEST_MONGODB_URL="mongodb://localhost:${MONGO_PORT}/ceilometer"
if test -n "$CEILOMETER_TEST_HBASE_URL"
then
    export CEILOMETER_TEST_HBASE_TABLE_PREFIX=$(hexdump -n 16 -v -e '/1 "%02X"' /dev/urandom)
    python tools/test_hbase_table_utils.py --upgrade
fi

export ZAQAR_TEST_MONGODB=1
export ZAQAR_TEST_SLOW=1

# Yield execution to venv command
$*
