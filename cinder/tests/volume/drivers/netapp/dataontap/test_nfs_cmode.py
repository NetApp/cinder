# Copyright (c) 2014 Andrew Kerr.  All rights reserved.
# Copyright (c) 2015 Tom Barron.  All rights reserved.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
Mock unit tests for the NetApp cmode nfs storage driver
"""

import mock
from oslo_log import log as logging

from cinder.brick.remotefs import remotefs as remotefs_brick
from cinder import exception
from cinder.openstack.common import loopingcall
from cinder import test
from cinder.tests.volume.drivers.netapp.dataontap import fakes as fake
from cinder.tests.volume.drivers.netapp import fakes as na_fakes
from cinder import utils
from cinder.volume.drivers.netapp.dataontap.client import api as netapp_api
from cinder.volume.drivers.netapp.dataontap.client import client_cmode
from cinder.volume.drivers.netapp.dataontap import nfs_base
from cinder.volume.drivers.netapp.dataontap import nfs_cmode
from cinder.volume.drivers.netapp.dataontap import ssc_cmode
from cinder.volume.drivers.netapp import utils as na_utils
from cinder.volume.drivers import nfs
from cinder.volume import utils as volume_utils


LOG = logging.getLogger(__name__)


class NetAppCmodeNfsDriverTestCase(test.TestCase):
    def setUp(self):
        super(NetAppCmodeNfsDriverTestCase, self).setUp()

        kwargs = {'configuration': self.get_config_cmode()}

        with mock.patch.object(utils, 'get_root_helper',
                               return_value=mock.Mock()):
            with mock.patch.object(remotefs_brick, 'RemoteFsClient',
                                   return_value=mock.Mock()):
                self.driver = nfs_cmode.NetAppCmodeNfsDriver(**kwargs)
                self.driver.vserver = fake.VSERVER_NAME
                self.driver.ssc_enabled = True
                self.driver._mounted_shares = [fake.NFS_SHARE]
                self.driver.ssc_vols = True

    def get_config_cmode(self):
        config = na_fakes.create_configuration_cmode()
        config.netapp_storage_protocol = 'nfs'
        config.netapp_login = 'admin'
        config.netapp_password = 'pass'
        config.netapp_server_hostname = '127.0.0.1'
        config.netapp_transport_type = 'http'
        config.netapp_server_port = '80'
        config.netapp_vserver = fake.VSERVER_NAME
        return config

    @mock.patch.object(client_cmode, 'Client', mock.Mock())
    @mock.patch.object(nfs.NfsDriver, 'do_setup')
    @mock.patch.object(na_utils, 'check_flags')
    def test_do_setup(self, mock_check_flags, mock_super_do_setup):
        self.driver.do_setup(mock.Mock())

        self.assertTrue(mock_check_flags.called)
        self.assertTrue(mock_super_do_setup.called)

    def test_check_for_setup_error(self):
        super_check_for_setup_error = self.mock_object(
            nfs_base.NetAppNfsDriver, 'check_for_setup_error')
        mock_check_ssc_api_permissions = self.mock_object(
            ssc_cmode, 'check_ssc_api_permissions')
        mock_start_periodic_tasks = self.mock_object(
            self.driver, '_start_periodic_tasks')
        self.driver.zapi_client = mock.Mock()

        self.driver.check_for_setup_error()

        self.assertEqual(1, super_check_for_setup_error.call_count)
        mock_check_ssc_api_permissions.assert_called_once_with(
            self.driver.zapi_client)
        self.assertEqual(1, mock_start_periodic_tasks.call_count)

    def test_do_qos_for_volume_no_exception(self):

        mock_get_info = self.mock_object(na_utils,
                                         'get_valid_qos_policy_group_info')
        mock_get_info.return_value = fake.QOS_POLICY_GROUP_INFO
        self.driver.zapi_client = mock.Mock()
        mock_provision_qos = self.driver.zapi_client.provision_qos_policy_group
        mock_set_policy = self.mock_object(self.driver,
                                           '_set_qos_policy_group_on_volume')
        mock_error_log = self.mock_object(nfs_cmode.LOG, 'error')
        mock_debug_log = self.mock_object(nfs_cmode.LOG, 'debug')
        mock_cleanup = self.mock_object(self.driver,
                                        '_cleanup_volume_on_failure')

        self.driver._do_qos_for_volume(fake.NFS_VOLUME, fake.EXTRA_SPECS)

        mock_get_info.assert_has_calls([
            mock.call(fake.NFS_VOLUME, fake.EXTRA_SPECS)])
        mock_provision_qos.assert_has_calls([
            mock.call(fake.QOS_POLICY_GROUP_INFO)])
        mock_set_policy.assert_has_calls([
            mock.call(fake.NFS_VOLUME, fake.QOS_POLICY_GROUP_INFO)])
        self.assertEqual(0, mock_error_log.call_count)
        self.assertEqual(0, mock_debug_log.call_count)
        self.assertEqual(0, mock_cleanup.call_count)

    def test_do_qos_for_volume_exception_w_cleanup(self):
        mock_get_info = self.mock_object(na_utils,
                                         'get_valid_qos_policy_group_info')
        mock_get_info.return_value = fake.QOS_POLICY_GROUP_INFO
        self.driver.zapi_client = mock.Mock()
        mock_provision_qos = self.driver.zapi_client.provision_qos_policy_group
        mock_set_policy = self.mock_object(self.driver,
                                           '_set_qos_policy_group_on_volume')
        mock_set_policy.side_effect = netapp_api.NaApiError
        mock_error_log = self.mock_object(nfs_cmode.LOG, 'error')
        mock_debug_log = self.mock_object(nfs_cmode.LOG, 'debug')
        mock_cleanup = self.mock_object(self.driver,
                                        '_cleanup_volume_on_failure')

        self.assertRaises(netapp_api.NaApiError,
                          self.driver._do_qos_for_volume,
                          fake.NFS_VOLUME,
                          fake.EXTRA_SPECS)

        mock_get_info.assert_has_calls([
            mock.call(fake.NFS_VOLUME, fake.EXTRA_SPECS)])
        mock_provision_qos.assert_has_calls([
            mock.call(fake.QOS_POLICY_GROUP_INFO)])
        mock_set_policy.assert_has_calls([
            mock.call(fake.NFS_VOLUME, fake.QOS_POLICY_GROUP_INFO)])
        self.assertEqual(1, mock_error_log.call_count)
        self.assertEqual(1, mock_debug_log.call_count)
        mock_cleanup.assert_has_calls([
            mock.call(fake.NFS_VOLUME)])

    def test_do_qos_for_volume_exception_no_cleanup(self):

        mock_get_info = self.mock_object(na_utils,
                                         'get_valid_qos_policy_group_info')
        mock_get_info.side_effect = exception.Invalid
        self.driver.zapi_client = mock.Mock()
        mock_provision_qos = self.driver.zapi_client.provision_qos_policy_group
        mock_set_policy = self.mock_object(self.driver,
                                           '_set_qos_policy_group_on_volume')
        mock_error_log = self.mock_object(nfs_cmode.LOG, 'error')
        mock_debug_log = self.mock_object(nfs_cmode.LOG, 'debug')
        mock_cleanup = self.mock_object(self.driver,
                                        '_cleanup_volume_on_failure')

        self.assertRaises(exception.Invalid, self.driver._do_qos_for_volume,
                          fake.NFS_VOLUME, fake.EXTRA_SPECS, cleanup=False)

        mock_get_info.assert_has_calls([
            mock.call(fake.NFS_VOLUME, fake.EXTRA_SPECS)])
        self.assertEqual(0, mock_provision_qos.call_count)
        self.assertEqual(0, mock_set_policy.call_count)
        self.assertEqual(1, mock_error_log.call_count)
        self.assertEqual(0, mock_debug_log.call_count)
        self.assertEqual(0, mock_cleanup.call_count)

    def test_set_qos_policy_group_on_volume(self):

        mock_get_name_from_info = self.mock_object(
            na_utils, 'get_qos_policy_group_name_from_info')
        mock_get_name_from_info.return_value = fake.QOS_POLICY_GROUP_NAME

        mock_extract_host = self.mock_object(volume_utils, 'extract_host')
        mock_extract_host.return_value = fake.NFS_SHARE

        self.driver.zapi_client = mock.Mock()
        mock_get_flex_vol_name =\
            self.driver.zapi_client.get_vol_by_junc_vserver
        mock_get_flex_vol_name.return_value = fake.FLEXVOL

        mock_file_assign_qos = self.driver.zapi_client.file_assign_qos

        self.driver._set_qos_policy_group_on_volume(fake.NFS_VOLUME,
                                                    fake.QOS_POLICY_GROUP_INFO)

        mock_get_name_from_info.assert_has_calls([
            mock.call(fake.QOS_POLICY_GROUP_INFO)])
        mock_extract_host.assert_has_calls([
            mock.call(fake.NFS_HOST_STRING, level='pool')])
        mock_get_flex_vol_name.assert_has_calls([
            mock.call(fake.VSERVER_NAME, fake.EXPORT_PATH)])
        mock_file_assign_qos.assert_has_calls([
            mock.call(fake.FLEXVOL, fake.QOS_POLICY_GROUP_NAME,
                      fake.NFS_VOLUME['name'])])

    def test_set_qos_policy_group_on_volume_no_info(self):

        mock_get_name_from_info = self.mock_object(
            na_utils, 'get_qos_policy_group_name_from_info')

        mock_extract_host = self.mock_object(volume_utils, 'extract_host')

        self.driver.zapi_client = mock.Mock()
        mock_get_flex_vol_name =\
            self.driver.zapi_client.get_vol_by_junc_vserver

        mock_file_assign_qos = self.driver.zapi_client.file_assign_qos

        self.driver._set_qos_policy_group_on_volume(fake.NFS_VOLUME,
                                                    None)

        self.assertEqual(0, mock_get_name_from_info.call_count)
        self.assertEqual(0, mock_extract_host.call_count)
        self.assertEqual(0, mock_get_flex_vol_name.call_count)
        self.assertEqual(0, mock_file_assign_qos.call_count)

    def test_set_qos_policy_group_on_volume_no_name(self):

        mock_get_name_from_info = self.mock_object(
            na_utils, 'get_qos_policy_group_name_from_info')
        mock_get_name_from_info.return_value = None

        mock_extract_host = self.mock_object(volume_utils, 'extract_host')

        self.driver.zapi_client = mock.Mock()
        mock_get_flex_vol_name =\
            self.driver.zapi_client.get_vol_by_junc_vserver

        mock_file_assign_qos = self.driver.zapi_client.file_assign_qos

        self.driver._set_qos_policy_group_on_volume(fake.NFS_VOLUME,
                                                    fake.QOS_POLICY_GROUP_INFO)

        mock_get_name_from_info.assert_has_calls([
            mock.call(fake.QOS_POLICY_GROUP_INFO)])
        self.assertEqual(0, mock_extract_host.call_count)
        self.assertEqual(0, mock_get_flex_vol_name.call_count)
        self.assertEqual(0, mock_file_assign_qos.call_count)

    def test_unmanage(self):
        mock_get_info = self.mock_object(na_utils,
                                         'get_valid_qos_policy_group_info')
        mock_get_info.return_value = fake.QOS_POLICY_GROUP_INFO

        self.driver.zapi_client = mock.Mock()
        mock_mark_for_deletion =\
            self.driver.zapi_client.mark_qos_policy_group_for_deletion

        super_unmanage = self.mock_object(nfs_base.NetAppNfsDriver, 'unmanage')

        self.driver.unmanage(fake.NFS_VOLUME)

        mock_get_info.assert_has_calls([mock.call(fake.NFS_VOLUME)])
        mock_mark_for_deletion.assert_has_calls([
            mock.call(fake.QOS_POLICY_GROUP_INFO)])
        super_unmanage.assert_has_calls([mock.call(fake.NFS_VOLUME)])

    def test_unmanage_invalid_qos(self):
        mock_get_info = self.mock_object(na_utils,
                                         'get_valid_qos_policy_group_info')
        mock_get_info.side_effect = exception.Invalid

        super_unmanage = self.mock_object(nfs_base.NetAppNfsDriver, 'unmanage')

        self.driver.unmanage(fake.NFS_VOLUME)

        mock_get_info.assert_has_calls([mock.call(fake.NFS_VOLUME)])
        super_unmanage.assert_has_calls([mock.call(fake.NFS_VOLUME)])

    def test_create_volume(self):
        self.mock_object(self.driver, '_ensure_shares_mounted')
        self.mock_object(na_utils, 'get_volume_extra_specs')
        self.mock_object(self.driver, '_do_create_volume')
        self.mock_object(self.driver, '_do_qos_for_volume')
        update_ssc = self.mock_object(self.driver, '_update_stale_vols')
        self.mock_object(self.driver, '_get_vol_for_share')
        expected = {'provider_location': fake.NFS_SHARE}

        result = self.driver.create_volume(fake.NFS_VOLUME)

        self.assertEqual(expected, result)
        self.assertEqual(1, update_ssc.call_count)

    def test_create_volume_exception(self):
        self.mock_object(self.driver, '_ensure_shares_mounted')
        self.mock_object(na_utils, 'get_volume_extra_specs')
        mock_create = self.mock_object(self.driver, '_do_create_volume')
        mock_create.side_effect = Exception
        update_ssc = self.mock_object(self.driver, '_update_stale_vols')
        self.mock_object(self.driver, '_get_vol_for_share')

        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume,
                          fake.NFS_VOLUME)

        self.assertEqual(1, update_ssc.call_count)

    def test_start_periodic_tasks(self):

        self.driver.zapi_client = mock.Mock()
        mock_remove_unused_qos_policy_groups = self.mock_object(
            self.driver.zapi_client,
            'remove_unused_qos_policy_groups')

        harvest_qos_periodic_task = mock.Mock()
        mock_loopingcall = self.mock_object(
            loopingcall,
            'FixedIntervalLoopingCall',
            mock.Mock(side_effect=[harvest_qos_periodic_task]))

        self.driver._start_periodic_tasks()

        mock_loopingcall.assert_has_calls([
            mock.call(mock_remove_unused_qos_policy_groups)])
        self.assertTrue(harvest_qos_periodic_task.start.called)

    def test_delete_volume(self):
        fake_provider_location = 'fake_provider_location'
        fake_volume = {'provider_location': fake_provider_location}
        self.mock_object(self.driver, '_delete_backing_file_for_volume')
        self.mock_object(na_utils, 'get_valid_qos_policy_group_info')
        self.driver.zapi_client = mock.Mock()
        mock_prov_deprov = self.mock_object(self.driver,
                                            '_post_prov_deprov_in_ssc')

        self.driver.delete_volume(fake_volume)

        mock_prov_deprov.assert_called_once_with(fake_provider_location)

    def test_delete_volume_exception_path(self):
        fake_provider_location = 'fake_provider_location'
        fake_volume = {'provider_location': fake_provider_location}
        self.mock_object(self.driver, '_delete_backing_file_for_volume')
        self.driver.zapi_client = mock.Mock(side_effect=[Exception])
        mock_prov_deprov = self.mock_object(self.driver,
                                            '_post_prov_deprov_in_ssc')

        self.driver.delete_volume(fake_volume)

        mock_prov_deprov.assert_called_once_with(fake_provider_location)

    def test_delete_backing_file_for_volume(self):
        mock_filer_delete = self.mock_object(self.driver,
                                             '_delete_volume_on_filer')
        mock_super_delete = self.mock_object(nfs_base.NetAppNfsDriver,
                                             'delete_volume')

        self.driver._delete_backing_file_for_volume(fake.NFS_VOLUME)

        mock_filer_delete.assert_called_once_with(fake.NFS_VOLUME)
        self.assertEqual(0, mock_super_delete.call_count)

    def test_delete_backing_file_for_volume_exception_path(self):
        mock_filer_delete = self.mock_object(self.driver,
                                             '_delete_volume_on_filer')
        mock_filer_delete.side_effect = [Exception]
        mock_super_delete = self.mock_object(nfs_base.NetAppNfsDriver,
                                             'delete_volume')

        self.driver._delete_backing_file_for_volume(fake.NFS_VOLUME)

        mock_filer_delete.assert_called_once_with(fake.NFS_VOLUME)
        mock_super_delete.assert_called_once_with(fake.NFS_VOLUME)

    def test_delete_volume_on_filer(self):
        mock_get_vs_ip = self.mock_object(self.driver, '_get_export_ip_path')
        mock_get_vs_ip.return_value = (fake.VSERVER_NAME, '/%s' % fake.FLEXVOL)
        self.driver.zapi_client = mock.Mock()
        mock_zapi_delete = self.driver.zapi_client.delete_file

        self.driver._delete_volume_on_filer(fake.NFS_VOLUME)

        mock_zapi_delete.assert_called_once_with(
            '/vol/%s/%s' % (fake.FLEXVOL, fake.NFS_VOLUME['name']))

    def test_delete_snapshot(self):
        mock_get_location = self.mock_object(self.driver,
                                             '_get_provider_location')
        mock_get_location.return_value = fake.PROVIDER_LOCATION

        mock_delete_backing = self.mock_object(
            self.driver, '_delete_backing_file_for_snapshot')

        mock_prov_deprov = self.mock_object(self.driver,
                                            '_post_prov_deprov_in_ssc')

        self.driver.delete_snapshot(fake.test_snapshot)

        mock_delete_backing.assert_called_once_with(fake.test_snapshot)
        mock_prov_deprov.assert_called_once_with(fake.PROVIDER_LOCATION)

    def test_delete_backing_file_for_snapshot(self):
        mock_filer_delete = self.mock_object(
            self.driver, '_delete_snapshot_on_filer')
        mock_super_delete = self.mock_object(nfs_base.NetAppNfsDriver,
                                             'delete_snapshot')

        self.driver._delete_backing_file_for_snapshot(fake.test_snapshot)

        mock_filer_delete.assert_called_once_with(fake.test_snapshot)
        self.assertEqual(0, mock_super_delete.call_count)

    def test_delete_backing_file_for_snapshot_exception_path(self):
        mock_filer_delete = self.mock_object(
            self.driver, '_delete_snapshot_on_filer')
        mock_filer_delete.side_effect = [Exception]
        mock_super_delete = self.mock_object(nfs_base.NetAppNfsDriver,
                                             'delete_snapshot')

        self.driver._delete_backing_file_for_snapshot(fake.test_snapshot)

        mock_filer_delete.assert_called_once_with(fake.test_snapshot)
        mock_super_delete.assert_called_once_with(fake.test_snapshot)

    def test_delete_snapshot_on_filer(self):
        mock_get_vs_ip = self.mock_object(self.driver, '_get_export_ip_path')
        mock_get_vs_ip.return_value = (fake.VSERVER_NAME, '/%s' % fake.FLEXVOL)
        self.driver.zapi_client = mock.Mock()
        mock_zapi_delete = self.driver.zapi_client.delete_file

        self.driver._delete_snapshot_on_filer(fake.test_snapshot)

        mock_zapi_delete.assert_called_once_with(
            '/vol/%s/%s' % (fake.FLEXVOL, fake.test_snapshot['name']))

    def test_get_vol_for_share(self):
        fake_volume = fake.test_volume
        ssc_vols = {'all': {fake_volume}}

        with mock.patch.object(self.driver, 'ssc_vols', ssc_vols):
            result = self.driver._get_vol_for_share(fake.NFS_SHARE)

        self.assertEqual(fake.test_volume, result)

    def test_get_vol_for_share_no_ssc_vols(self):
        with mock.patch.object(self.driver, 'ssc_vols', None):
            self.assertIsNone(self.driver._get_vol_for_share(fake.NFS_SHARE))
