#!/bin/bash
#
# lib/zaqar
# Install and start **Zaqar** service

# To enable a minimal set of Zaqar services, add the following to localrc:
#
#     enable_service zaqar-websocket zaqar-wsgi
#
# Dependencies:
# - functions
# - OS_AUTH_URL for auth in api
# - DEST set to the destination directory
# - SERVICE_PASSWORD, SERVICE_TENANT_NAME for auth in api
# - STACK_USER service user

# stack.sh
# ---------
# install_zaqar
# configure_zaqar
# init_zaqar
# start_zaqar
# stop_zaqar
# cleanup_zaqar
# cleanup_zaqar_mongodb

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set +o xtrace


# Defaults
# --------

# Set up default directories
ZAQAR_DIR=$DEST/zaqar
ZAQARCLIENT_DIR=$DEST/python-zaqarclient
ZAQAR_CONF_DIR=/etc/zaqar
ZAQAR_CONF=$ZAQAR_CONF_DIR/zaqar.conf
ZAQAR_UWSGI_CONF=$ZAQAR_CONF_DIR/uwsgi.conf
ZAQAR_API_LOG_DIR=/var/log/zaqar
ZAQAR_API_LOG_FILE=$ZAQAR_API_LOG_DIR/queues.log
ZAQAR_AUTH_CACHE_DIR=${ZAQAR_AUTH_CACHE_DIR:-/var/cache/zaqar}

# Support potential entry-points console scripts
ZAQAR_BIN_DIR=$(get_python_exec_prefix)

# Set up database backend
ZAQAR_BACKEND=${ZAQAR_BACKEND:-mongodb}


# Set Zaqar repository
ZAQAR_REPO=${ZAQAR_REPO:-${GIT_BASE}/openstack/zaqar.git}
ZAQAR_BRANCH=${ZAQAR_BRANCH:-master}

# Set client library repository
ZAQARCLIENT_REPO=${ZAQARCLIENT_REPO:-${GIT_BASE}/openstack/python-zaqarclient.git}
ZAQARCLIENT_BRANCH=${ZAQARCLIENT_BRANCH:-master}

# Set Zaqar Connection Info
ZAQAR_SERVICE_HOST=${ZAQAR_SERVICE_HOST:-$SERVICE_HOST}
ZAQAR_SERVICE_PORT=${ZAQAR_SERVICE_PORT:-8888}
ZAQAR_WEBSOCKET_PORT=${ZAQAR_WEBSOCKET_PORT:-9000}
ZAQAR_SERVICE_PROTOCOL=${ZAQAR_SERVICE_PROTOCOL:-$SERVICE_PROTOCOL}

# Tell Tempest this project is present
TEMPEST_SERVICES+=,zaqar


# Functions
# ---------

# Test if any Zaqar services are enabled
# is_zaqar_enabled
function is_zaqar_enabled {
    [[ ,${ENABLED_SERVICES} =~ ,"zaqar" ]] && return 0
    return 1
}

# cleanup_zaqar() - Cleans up general things from previous
# runs and storage specific left overs.
function cleanup_zaqar {
    if [ "$ZAQAR_BACKEND" = 'mongodb' ] ; then
        cleanup_zaqar_mongodb
    fi
}

# cleanup_zaqar_mongodb() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_zaqar_mongodb {
    if ! timeout $SERVICE_TIMEOUT sh -c "while ! mongo zaqar --eval 'db.dropDatabase();'; do sleep 1; done"; then
        die $LINENO "Mongo DB did not start"
    else
        full_version=$(mongo zaqar --eval 'db.dropDatabase();')
        mongo_version=`echo $full_version | cut -d' ' -f4`
        required_mongo_version='2.2'
        if [[ $mongo_version < $required_mongo_version ]]; then
            die $LINENO "Zaqar needs Mongo DB version >= 2.2 to run."
        fi
    fi
}

# configure_zaqarclient() - Set config files, create data dirs, etc
function configure_zaqarclient {
    setup_develop $ZAQARCLIENT_DIR
}

# configure_zaqar() - Set config files, create data dirs, etc
function configure_zaqar {
    setup_develop $ZAQAR_DIR

    [ ! -d $ZAQAR_CONF_DIR ] && sudo mkdir -m 755 -p $ZAQAR_CONF_DIR
    sudo chown $USER $ZAQAR_CONF_DIR

    [ ! -d $ZAQAR_API_LOG_DIR ] &&  sudo mkdir -m 755 -p $ZAQAR_API_LOG_DIR
    sudo chown $USER $ZAQAR_API_LOG_DIR

    iniset $ZAQAR_CONF DEFAULT debug True
    iniset $ZAQAR_CONF DEFAULT verbose True
    iniset $ZAQAR_CONF DEFAULT unreliable True
    iniset $ZAQAR_CONF DEFAULT admin_mode True
    iniset $ZAQAR_CONF DEFAULT use_syslog $SYSLOG
    iniset $ZAQAR_CONF DEFAULT auth_strategy keystone
    iniset $ZAQAR_CONF signed_url secret_key notreallysecret

    iniset $ZAQAR_CONF storage message_pipeline zaqar.notification.notifier

    # Enable pooling by default for now
    iniset $ZAQAR_CONF DEFAULT admin_mode True
    iniset $ZAQAR_CONF 'drivers:transport:websocket' bind $ZAQAR_SERVICE_HOST
    iniset $ZAQAR_CONF 'drivers:transport:websocket' port $ZAQAR_WEBSOCKET_PORT
    iniset $ZAQAR_CONF drivers transport websocket

    configure_auth_token_middleware $ZAQAR_CONF zaqar $ZAQAR_AUTH_CACHE_DIR

    if [ "$ZAQAR_BACKEND" = 'mongodb' ] ; then
        iniset $ZAQAR_CONF DEFAULT pooling True
        iniset $ZAQAR_CONF 'pooling:catalog' enable_virtual_pool True
        iniset $ZAQAR_CONF  drivers message_store mongodb
        iniset $ZAQAR_CONF 'drivers:message_store:mongodb' uri mongodb://localhost:27017/zaqar
        iniset $ZAQAR_CONF 'drivers:message_store:mongodb' database zaqar

        iniset $ZAQAR_CONF  drivers management_store mongodb
        iniset $ZAQAR_CONF 'drivers:management_store:mongodb' uri mongodb://localhost:27017/zaqar_mgmt
        iniset $ZAQAR_CONF 'drivers:management_store:mongodb' database zaqar_mgmt
        configure_mongodb
    elif [ "$ZAQAR_BACKEND" = 'redis' ] ; then
        iniset $ZAQAR_CONF  drivers message_store redis
        iniset $ZAQAR_CONF 'drivers:message_store:redis' uri redis://localhost:6379
        iniset $ZAQAR_CONF 'drivers:message_store:redis' database zaqar
        configure_redis
    fi

    if is_service_enabled qpid || [ -n "$RABBIT_HOST" ] && [ -n "$RABBIT_PASSWORD" ]; then
        iniset $ZAQAR_CONF DEFAULT notification_driver messaging
        iniset $ZAQAR_CONF DEFAULT control_exchange zaqar
    fi
    iniset_rpc_backend zaqar $ZAQAR_CONF DEFAULT

    pip_install uwsgi
    iniset $ZAQAR_UWSGI_CONF uwsgi http $ZAQAR_SERVICE_HOST:$ZAQAR_SERVICE_PORT
    iniset $ZAQAR_UWSGI_CONF uwsgi processes 1
    iniset $ZAQAR_UWSGI_CONF uwsgi threads 4
    iniset $ZAQAR_UWSGI_CONF uwsgi wsgi-file $ZAQAR_DIR/zaqar/transport/wsgi/app.py
    iniset $ZAQAR_UWSGI_CONF uwsgi callable app

    cleanup_zaqar
}

function configure_redis {
    if is_ubuntu; then
        install_package redis-server
        pip_install redis
    elif is_fedora; then
        install_package redis
        pip_install redis
    else
        exit_distro_not_supported "redis installation"
    fi
}

function configure_mongodb {
    # Set nssize to 2GB. This increases the number of namespaces supported
    # # per database.
    pip_install pymongo
    if is_ubuntu; then
        install_package mongodb-server
        sudo sed -i -e "
            s|[^ \t]*#[ \t]*\(nssize[ \t]*=.*\$\)|\1|
            s|^\(nssize[ \t]*=[ \t]*\).*\$|\1 2047|
        " /etc/mongodb.conf
        restart_service mongodb
    elif is_fedora; then
        install_package mongodb
        install_package mongodb-server
        sudo sed -i '/--nssize/!s/OPTIONS=\"/OPTIONS=\"--nssize 2047 /' /etc/sysconfig/mongod
        restart_service mongod
    fi
}

# init_zaqar() - Initialize etc.
function init_zaqar {
    # Create cache dir
    sudo mkdir -p $ZAQAR_AUTH_CACHE_DIR
    sudo chown $STACK_USER $ZAQAR_AUTH_CACHE_DIR
    rm -f $ZAQAR_AUTH_CACHE_DIR/*
}

# install_zaqar() - Collect source and prepare
function install_zaqar {
    setup_develop $ZAQAR_DIR -e
}

# install_zaqarclient() - Collect source and prepare
function install_zaqarclient {
    git_clone $ZAQARCLIENT_REPO $ZAQARCLIENT_DIR $ZAQARCLIENT_BRANCH
    setup_develop $ZAQARCLIENT_DIR
}

# start_zaqar() - Start running processes, including screen
function start_zaqar {
    if [[ "$USE_SCREEN" = "False" ]]; then
        run_process zaqar-wsgi "uwsgi --ini $ZAQAR_UWSGI_CONF --daemonize $ZAQAR_API_LOG_DIR/uwsgi.log"
        run_process zaqar-websocket "zaqar-server --config-file $ZAQAR_CONF --daemon"
    else
        run_process zaqar-wsgi "uwsgi --ini $ZAQAR_UWSGI_CONF"
        run_process zaqar-websocket "zaqar-server --config-file $ZAQAR_CONF"
    fi

    echo "Waiting for Zaqar to start..."
    token=$(openstack token issue -c id -f value)
    if ! timeout $SERVICE_TIMEOUT sh -c "while ! wget --no-proxy -q --header=\"X-Auth-Token:$token\" -O- $ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_SERVICE_PORT/v2/ping; do sleep 1; done"; then
        die $LINENO "Zaqar did not start"
    fi
}

# stop_zaqar() - Stop running processes
function stop_zaqar {
    local serv
    # Kill the zaqar screen windows
    for serv in zaqar-wsgi zaqar-websocket; do
        screen -S $SCREEN_NAME -p $serv -X kill
    done
}

function create_zaqar_accounts {
    create_service_user "zaqar"

    if [[ "$KEYSTONE_CATALOG_BACKEND" = 'sql' ]]; then

        local zaqar_service=$(get_or_create_service "zaqar" \
            "messaging" "Zaqar Service")
        get_or_create_endpoint $zaqar_service \
            "$REGION_NAME" \
            "$ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_SERVICE_PORT" \
            "$ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_SERVICE_PORT" \
            "$ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_SERVICE_PORT"

        local zaqar_ws_service=$(get_or_create_service "zaqar-websocket" \
            "messaging-websocket" "Zaqar Websocket Service")
        get_or_create_endpoint $zaqar_ws_service \
            "$REGION_NAME" \
            "$ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_WEBSOCKET_PORT" \
            "$ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_WEBSOCKET_PORT" \
            "$ZAQAR_SERVICE_PROTOCOL://$ZAQAR_SERVICE_HOST:$ZAQAR_WEBSOCKET_PORT"
    fi

}

if is_service_enabled zaqar-websocket || is_service_enabled zaqar-wsgi; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Zaqar"
        install_zaqarclient
        install_zaqar
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configuring Zaqar"
        configure_zaqar
        configure_zaqarclient

        if is_service_enabled key; then
           create_zaqar_accounts
        fi

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        echo_summary "Initializing Zaqar"
        init_zaqar
        start_zaqar
    fi

    if [[ "$1" == "unstack" ]]; then
        stop_zaqar
    fi
fi

# Restore xtrace
$XTRACE

# Local variables:
# mode: shell-script
# End:
