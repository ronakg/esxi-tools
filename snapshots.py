#!/usr/bin/env python

import atexit
import argparse
import sys
import time
import ssl

try:
    from pyVmomi import vim, vmodl
    from pyVim.task import WaitForTask
    from pyVim import connect
    from pyVim.connect import Disconnect, SmartConnect, GetSi
except ImportError:
    print('\'pyvmomi\' is not installed. Install it using \'pip install pyvmomi\' same and try again.')
    sys.exit(1)

SNAPS_LIST = 'snaps_list'
SNAPS_CREATE = 'snaps_create'
SNAPS_DELETE = 'snaps_delete'
SNAPS_SWITCH = 'snaps_switch'
QUIT = 'quit'

SNAPS_MENU = (
    (SNAPS_LIST, 'List Snapshots'),
    (SNAPS_CREATE, 'Create Snapshot'),
    (SNAPS_SWITCH, 'Switch to Snapshot'),
    (SNAPS_DELETE, 'Delete Snapshot'),
    (QUIT, 'Quit')
)


def get_obj(content, vimtype, name):
    """
     Get the vsphere object associated with a given text name
    """
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if c.name == name:
            obj = c
            break
    return obj


def list_snapshots_recursively(snapshots):
    snapshot_data = []
    snap_text = ""
    for snapshot in snapshots:
        snapshot_data.append((snapshot.name, snapshot.createTime))
        snapshot_data = snapshot_data + list_snapshots_recursively(
                                        snapshot.childSnapshotList)
    return snapshot_data


def get_current_snap_obj(snapshots, snapob):
    snap_obj = []
    for snapshot in snapshots:
        if snapshot.snapshot == snapob:
            snap_obj.append(snapshot)
        snap_obj = snap_obj + get_current_snap_obj(
                                snapshot.childSnapshotList, snapob)
    return snap_obj


def get_snapshots_by_name_recursively(snapshots, snapname):
    snap_obj = []
    for snapshot in snapshots:
        if snapshot.name == snapname:
            snap_obj.append(snapshot)
        else:
            snap_obj = snap_obj + get_snapshots_by_name_recursively(
                                    snapshot.childSnapshotList, snapname)
    return snap_obj


def parse_args():
    parser = argparse.ArgumentParser(description='Utility to manage VMs on vCenter Server')
    parser.add_argument('--vc_server', required=True, help='vCenter hostname or IP')
    parser.add_argument('--vm_name', required=True, help='Name of the Virtual Machine')
    parser.add_argument('--username', required=True, help='Username for vCenter server')
    parser.add_argument('--password', required=True, help='Password for vCenter server username')

    return parser.parse_args()


def print_vm_info(vm, depth=1, max_depth=10):
    """
    Print information for a particular virtual machine or recurse into a
    folder with depth protection
    """

    # if this is a group it will have children. if it does, recurse into them
    # and then return
    if hasattr(vm, 'childEntity'):
        if depth > max_depth:
            return
        vmList = vm.childEntity
        return

    summary = vm.summary
    current_snapref = vm.snapshot.currentSnapshot
    current_snap_obj = get_current_snap_obj(
                        vm.snapshot.rootSnapshotList, current_snapref)
    print("    Name       : {}".format(summary.config.name))
    print("    Guest      : {}".format(summary.config.guestFullName))
    print("    State      : {}".format(summary.runtime.powerState))
    if current_snap_obj[0].description:
        curr_snap_name = '{} ({})'.format(current_snap_obj[0].name, current_snap_obj[0].description)
    else:
        curr_snap_name = '{}'.format(current_snap_obj[0].name)
    print('    Snapshot   : {}'.format(curr_snap_name))
    if summary.guest is not None:
        ip = summary.guest.ipAddress
        if ip:
            print("    IP         : {}".format(ip))


def parse_service_instance(service_instance, vm_name):
    """
    Print some basic knowledge about your environment as a Hello World
    equivalent for pyVmomi
    """

    print('VM Properties')
    print('=============')
    content = service_instance.RetrieveContent()
    object_view = content.viewManager.CreateContainerView(content.rootFolder,
                                                          [], True)
    for obj in object_view.view:
        if isinstance(obj, vim.VirtualMachine):
            if obj.name == vm_name:
                print_vm_info(obj)

    object_view.Destroy()


def create_menu(menu, msg='Choose your operation'):
    for idx, item in enumerate(menu, start=1):
        print('  {}) {}'.format(idx, item[1]))

    op = None
    while True:
        try:
            op = int(raw_input('{} (between 1 and {}): '.format(msg, len(menu))))
        except ValueError as e:
            op = None
        finally:
            if op < 1 or op > len(menu):
                op = None
        if op:
            return menu[op-1][0]
        else:
            print('Invalid selection')


def choose_snapshot(vm, msg):
    print('List of available snapshots')
    print('===========================')
    snapshot_paths = list_snapshots_recursively(vm.snapshot.rootSnapshotList)
    snapshots_menu = []
    for snapshot in snapshot_paths:
        snapshots_menu.append((snapshot[0], snapshot[0]))
    if snapshots_menu:
        snap_to_delete = create_menu(snapshots_menu, msg)
        snap_obj = get_snapshots_by_name_recursively(
            vm.snapshot.rootSnapshotList, snap_to_delete)
        return snap_obj[0]
    else:
        return None


if __name__ =='__main__':
    args = parse_args()

    context = ssl._create_unverified_context()

    service_instance = connect.Connect(args.vc_server, 443,
                        args.username, args.password,
                        sslContext=context)

    atexit.register(Disconnect, service_instance)
    content = service_instance.RetrieveContent()

    parse_service_instance(service_instance, args.vm_name)

    vm = get_obj(content, [vim.VirtualMachine], args.vm_name)

    print('\nOperations')
    print('==========')
    op = create_menu(SNAPS_MENU)

    print('')

    if op == SNAPS_LIST:
        print('List of Snapshots on {}:'.format(args.vm_name))
        snapshot_paths = list_snapshots_recursively(vm.snapshot.rootSnapshotList)
        for snap in snapshot_paths:
            name, create_time = snap
            print('  - {}\t\tcreated on {}'.format(name, create_time))
    elif op == SNAPS_CREATE:
        new_snap_name = raw_input('Choose a name for new snapshot: ').strip()
        description = ''
        dump_mem = False
        quiesce = False
        print('Creating snapshot {} for VM {}'.format(new_snap_name, args.vm_name))
        WaitForTask(vm.CreateSnapshot(
                    new_snap_name, description, dump_mem, quiesce))
        print('New snapshot {} created successfully.'.format(new_snap_name))
    elif op == SNAPS_DELETE:
        snap_to_delete = choose_snapshot(vm, 'Choose snapshot to delete: ')
        if snap_to_delete:
            confirmation = raw_input('Are you sure you want to delete {}? (yes/no) '.format(snap_to_delete.name)).lower().strip() in ('y', 'yes')
            if confirmation:
                print('Deleting snapshot {}...'.format(snap_to_delete.name))
                WaitForTask(snap_to_delete.snapshot.RemoveSnapshot_Task(removeChildren=False))
                print('{} deleted successfully.'.format(snap_to_delete.name))
            else:
                print('Delete operation canceled.')
        else:
            print('No snapshots stored on the server.')
    elif op == SNAPS_SWITCH:
        snap_to_switch = choose_snapshot(vm, 'Choose snapshot to switch to: ')
        if snap_to_switch:
            confirmation = raw_input('Are you sure you want to switch to {}? (yes/no) '.format(snap_to_switch.name)).lower().strip() in ('y', 'yes')
            if confirmation:
                print('Switching to snapshot {}...'.format(snap_to_switch.name))
                WaitForTask(snap_to_switch.snapshot.RevertToSnapshot_Task())
                print('Switched to snapshot {} successfully.'.format(snap_to_switch.name))
                WaitForTask(vm.PowerOn())
                print('VM {} powered on successfully.'.format(vm.name))
        else:
            print('No snapshots stored on the server.')
    elif op == QUIT:
        pass
