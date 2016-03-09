# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_config import cfg
from oslo_log import log
from stevedore import driver

from zaqar.api import handler
from zaqar.common import cache as oslo_cache
from zaqar.common import configs
from zaqar.common import decorators
from zaqar.common import errors
from zaqar.storage import pipeline
from zaqar.storage import pooling
from zaqar.storage import utils as storage_utils
from zaqar.transport import base
from zaqar.transport import validation

from zaqar.i18n import _LE

LOG = log.getLogger(__name__)


_CLI_OPTIONS = (
    configs._ADMIN_MODE_OPT,
    cfg.BoolOpt('daemon', default=False,
                help='Run Zaqar server in the background.'),
)

# NOTE (Obulpathi): Register daemon command line option for
# zaqar-server
CONF = cfg.CONF
CONF.register_cli_opts(_CLI_OPTIONS)
log.register_options(CONF)


class Bootstrap(object):
    """Defines the Zaqar bootstrapper.

    The bootstrap loads up drivers per a given configuration, and
    manages their lifetimes.
    """

    def __init__(self, conf):
        self.conf = conf

        for group, opts in configs._config_options():
            self.conf.register_opts(opts, group=group)

        self.driver_conf = self.conf[configs._DRIVER_GROUP]

        log.setup(conf, 'zaqar')

    @decorators.lazy_property(write=False)
    def api(self):
        LOG.debug(u'Loading API handler')
        validate = validation.Validator(self.conf)
        defaults = base.ResourceDefaults(self.conf)
        return handler.Handler(self.storage, self.control, validate, defaults)

    @decorators.lazy_property(write=False)
    def storage(self):
        LOG.debug(u'Loading storage driver')
        if self.conf.pooling:
            LOG.debug(u'Storage pooling enabled')
            storage_driver = pooling.DataDriver(self.conf, self.cache,
                                                self.control)
        else:
            storage_driver = storage_utils.load_storage_driver(
                self.conf, self.cache, control_driver=self.control)

        LOG.debug(u'Loading storage pipeline')
        return pipeline.DataDriver(self.conf, storage_driver,
                                   self.control)

    @decorators.lazy_property(write=False)
    def control(self):
        LOG.debug(u'Loading storage control driver')
        return storage_utils.load_storage_driver(self.conf, self.cache,
                                                 control_mode=True)

    @decorators.lazy_property(write=False)
    def cache(self):
        LOG.debug(u'Loading proxy cache driver')
        try:
            oslo_cache.register_config(self.conf)
            return oslo_cache.get_cache(self.conf)
        except RuntimeError as exc:
            LOG.exception(exc)
            raise errors.InvalidDriver(exc)

    @decorators.lazy_property(write=False)
    def transport(self):
        transport_name = self.driver_conf.transport
        LOG.debug(u'Loading transport driver: %s', transport_name)

        # FIXME(vkmc): Find a better way to init args
        if transport_name == 'websocket':
            args = [self.conf, self.api, self.cache]
        else:
            args = [
                self.conf,
                self.storage,
                self.cache,
                self.control,
            ]

        try:
            mgr = driver.DriverManager('zaqar.transport',
                                       transport_name,
                                       invoke_on_load=True,
                                       invoke_args=args)
            return mgr.driver
        except RuntimeError as exc:
            LOG.exception(exc)
            LOG.error(_LE(u'Failed to load transport driver zaqar.transport.'
                          u'%(driver)s with args %(args)s'),
                      {'driver': transport_name, 'args': args})
            raise errors.InvalidDriver(exc)

    def run(self):
        self.transport.listen()
