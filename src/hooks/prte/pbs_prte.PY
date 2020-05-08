# coding: utf-8

# Copyright (C) 1994-2020 Altair Engineering, Inc.
# For more information, contact Altair at www.altair.com.
#
# This file is part of the PBS Professional ("PBS Pro") software.
#
# Open Source License Information:
#
# PBS Pro is free software. You can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# PBS Pro is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.
# See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Commercial License Information:
#
# For a copy of the commercial license terms and conditions,
# go to: (http://www.pbspro.com/UserArea/agreement.html)
# or contact the Altair Legal Department.
#
# Altair’s dual-license business model allows companies, individuals, and
# organizations to create proprietary derivative works of PBS Pro and
# distribute them - whether embedded or bundled with other software -
# under a commercial license agreement.
#
# Use of Altair’s trademarks, including but not limited to "PBS™",
# "PBS Professional®", and "PBS Pro™" and Altair’s logos is subject to Altair's
# trademark licensing policies.

"""
PBS for spawning the PMIx prted daemon on Linux execution hosts.
"""

# Module imports
#
# This one is needed to log messages
import pbs

# if we are not on a Linux system then the hook should always do nothing
# and accept, and certainly not try Linux-only module imports
import platform
if platform.system() != 'Linux':
    pbs.logmsg(pbs.EVENT_DEBUG,
               'Hook not on supported OS, accepting event')
    pbs.event().accept()
else:
    # Now we know that at least the hook might do something useful
    # so import other modules (some of them Linux-specific)
    # Note the else is needed to be PEP8-compliant:  the imports must
    # not be unindented since they are not top-of-file
    import sys
    import os
    import stat
    import errno
    import signal
    import subprocess
    import re
    import glob
    import time
    import string
    import traceback
    import copy
    import operator
    import fnmatch
    import math
    import types
    try:
        import json
    except Exception:
        import simplejson as json
    import fcntl
    import pwd

# Define some globals that get set in main
PBS_EXEC = ''
PBS_HOME = ''
PBS_MOM_HOME = ''
PBS_MOM_JOBS = ''

# ============================================================================
# Derived error classes
# ============================================================================


class AdminError(Exception):
    """
    Base class for errors fixable only by administrative action.
    """
    pass


class ProcessingError(Exception):
    """
    Base class for errors in processing, unknown cause.
    """
    pass


class UserError(Exception):
    """
    Base class for errors fixable by the user.
    """
    pass


class JobValueError(Exception):
    """
    Errors in PBS job resource values.
    """
    pass


# ============================================================================
# Utility functions
# ============================================================================

#
# FUNCTION caller_name
#
def caller_name():
    """
    Return the name of the calling function or method.
    """
    return str(sys._getframe(1).f_code.co_name)


def decode_list(data):
    """
    json hook to convert lists from non string type to str
    """
    ret = []
    for item in data:
        if isinstance(item, str):
            pass
        elif (sys.version_info[0] < 3) and isinstance(item, unicode):
            item = item.encode('utf-8')
        elif isinstance(item, (bytes, bytearray)):
            if sys.version_info[0] >= 3:
                item = str(item, 'utf-8')
            else:
                item = str(item)
        elif isinstance(item, list):
            item = decode_list(item)
        elif isinstance(item, dict):
            item = decode_dict(item)
        ret.append(item)
    return ret


def decode_dict(data):
    """
    json hook to convert dictionaries from non string type to str
    """
    ret = {}
    for key, value in list(data.items()):
        # first the key
        if isinstance(key, str):
            pass
        elif (sys.version_info[0] < 3) and isinstance(key, unicode):
            key = key.encode('utf-8')
        elif isinstance(key, (bytes, bytearray)):
            if sys.version_info[0] >= 3:
                key = str(key, 'utf-8')
            else:
                key = str(key)

        # now the value
        if isinstance(value, str):
            pass
        elif (sys.version_info[0] < 3) and isinstance(value, unicode):
            value = value.encode('utf-8')
        elif isinstance(value, (bytes, bytearray)):
            if sys.version_info[0] >= 3:
                value = str(value, 'utf-8')
            else:
                key = str(value)

        elif isinstance(value, list):
            value = decode_list(value)
        elif isinstance(value, dict):
            value = decode_dict(value)

        # add stringified (key, value) pair to result
        ret[key] = value
    return ret


def merge_dict(base, new):
    """
    Merge together two multilevel dictionaries where new
    takes precedence over base
    """
    if not isinstance(base, dict):
        raise ValueError('base must be type dict')
    if not isinstance(new, dict):
        raise ValueError('new must be type dict')
    newkeys = list(new.keys())
    merged = {}
    for key in base:
        if key in newkeys and isinstance(base[key], dict):
            # Take it off the list of keys to copy
            newkeys.remove(key)
            merged[key] = merge_dict(base[key], new[key])
        else:
            merged[key] = copy.deepcopy(base[key])
    # Copy the remaining unique keys from new
    for key in newkeys:
        merged[key] = copy.deepcopy(new[key])
    return merged


def printjob_info(jobid, include_attributes=False):
    """
    Use printjob to acquire the job information
    """
    info = {}
    jobfile = os.path.join(PBS_MOM_JOBS, '%s.JB' % jobid)
    if not os.path.isfile(jobfile):
        pbs.logmsg(pbs.EVENT_DEBUG4, 'File not found: %s' % (jobfile))
        return info
    cmd = [os.path.join(PBS_EXEC, 'bin', 'printjob')]
    if not include_attributes:
        cmd.append('-a')
    cmd.append(jobfile)
    try:
        pbs.logmsg(pbs.EVENT_DEBUG4, 'Running: %s' % cmd)
        process = subprocess.Popen(cmd, shell=False,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        out, err = process.communicate()
    except Exception as exc:
        pbs.logmsg(pbs.EVENT_DEBUG2, 'Error running command: %s' % cmd)
        pbs.logmsg(pbs.EVENT_DEBUG2, 'Error message: %s' % err)
        pbs.logmsg(pbs.EVENT_DEBUG2, 'Exception: %s' % exc)
        return info
    pattern = re.compile(r'^(\w.*):\s*(\S+)')
    if (not isinstance(out, str)
            and isinstance(out, (bytes, bytearray))):
        if sys.version_info[0] >= 3:
            out = out.decode('utf-8')
        else:
            out = str(out)

    for line in out.splitlines():
        result = re.match(pattern, line)
        if not result:
            continue
        key, val = result.groups()
        if not key or not val:
            continue
        if val.startswith('0x'):
            info[key] = int(val, 16)
        elif val.isdigit():
            info[key] = int(val)
        else:
            info[key] = val
    return info


def job_is_suspended(jobid):
    """
    Returns True if job is in a suspended or unknown substate
    """
    jobinfo = printjob_info(jobid)
    if 'substate' in jobinfo:
        return jobinfo['substate'] in [43, 45, 'unknown']
    return False


def job_is_running(jobid):
    """
    Returns True if job shows a running state and substate
    """
    jobinfo = printjob_info(jobid)
    if 'state' in jobinfo and jobinfo['state'] != 4:
        return False
    if 'substate' in jobinfo:
        return jobinfo['substate'] == 42
    return False


# ============================================================================
# Utility classes
# ============================================================================

#
# CLASS Lock
#
class Lock(object):
    """
    Implement a simple locking mechanism using a file lock
    """

    def __init__(self, path):
        self.path = path
        self.lockfd = None

    def getpath(self):
        """
        Return the path of the lock file.
        """
        return self.path

    def getlockfd(self):
        """
        Return the file descriptor of the lock file.
        """
        return self.lockfd

    def __enter__(self):
        self.lockfd = open(self.path, 'w')
        fcntl.flock(self.lockfd, fcntl.LOCK_EX)
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s file lock acquired by %s' %
                   (self.path, str(sys._getframe(1).f_code.co_name)))

    def __exit__(self, exc, val, trace):
        if self.lockfd:
            fcntl.flock(self.lockfd, fcntl.LOCK_UN)
            self.lockfd.close()
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s file lock released by %s' %
                   (self.path, str(sys._getframe(1).f_code.co_name)))


#
# CLASS HookUtils
#
class HookUtils(object):
    """
    Hook utility methods
    """

    def __init__(self, hook_events=None):
        if hook_events is not None:
            self.hook_events = hook_events
        else:
            # Defined in the order they appear in module_pbs_v1.c
            self.hook_events = {}
            self.hook_events[pbs.QUEUEJOB] = {
                'name': 'queuejob',
                'handler': None
            }
            self.hook_events[pbs.MODIFYJOB] = {
                'name': 'modifyjob',
                'handler': None
            }
            self.hook_events[pbs.RESVSUB] = {
                'name': 'resvsub',
                'handler': None
            }
            self.hook_events[pbs.MOVEJOB] = {
                'name': 'movejob',
                'handler': None
            }
            self.hook_events[pbs.RUNJOB] = {
                'name': 'runjob',
                'handler': None
            }
            self.hook_events[pbs.PROVISION] = {
                'name': 'provision',
                'handler': None
            }
            self.hook_events[pbs.EXECJOB_BEGIN] = {
                'name': 'execjob_begin',
                'handler': self._execjob_begin_handler
            }
            self.hook_events[pbs.EXECJOB_PROLOGUE] = {
                'name': 'execjob_prologue',
                'handler': None
            }
            self.hook_events[pbs.EXECJOB_EPILOGUE] = {
                'name': 'execjob_epilogue',
                'handler': self._execjob_epilogue_handler
            }
            self.hook_events[pbs.EXECJOB_PRETERM] = {
                'name': 'execjob_preterm',
                'handler': None
            }
            self.hook_events[pbs.EXECJOB_END] = {
                'name': 'execjob_end',
                'handler': self._execjob_end_handler
            }
            self.hook_events[pbs.EXECJOB_LAUNCH] = {
                'name': 'execjob_launch',
                'handler': self._execjob_launch_handler
            }
            self.hook_events[pbs.EXECHOST_PERIODIC] = {
                'name': 'exechost_periodic',
                'handler': self._exechost_periodic_handler
            }
            self.hook_events[pbs.EXECHOST_STARTUP] = {
                'name': 'exechost_startup',
                'handler': self._exechost_startup_handler
            }
            self.hook_events[pbs.EXECJOB_ATTACH] = {
                'name': 'execjob_attach',
                'handler': self._execjob_attach_handler
            }
            if hasattr(pbs, "EXECJOB_RESIZE"):
                self.hook_events[pbs.EXECJOB_RESIZE] = {
                    'name': 'execjob_resize',
                    'handler': self._execjob_resize_handler
                }
            if hasattr(pbs, "EXECJOB_ABORT"):
                self.hook_events[pbs.EXECJOB_ABORT] = {
                    'name': 'execjob_abort',
                    'handler': self._execjob_end_handler
                }
            if hasattr(pbs, "EXECJOB_POSTSUSPEND"):
                self.hook_events[pbs.EXECJOB_POSTSUSPEND] = {
                    'name': 'execjob_postsuspend',
                    'handler': self._execjob_postsuspend_handler
                }
            if hasattr(pbs, "EXECJOB_PRERESUME"):
                self.hook_events[pbs.EXECJOB_PRERESUME] = {
                    'name': 'execjob_preresume',
                    'handler': self._execjob_preresume_handler
                }
            self.hook_events[pbs.MOM_EVENTS] = {
                'name': 'mom_events',
                'handler': None
            }

    def __repr__(self):
        return 'HookUtils(%s)' % (repr(self.hook_events))

    @staticmethod
    def parse_config_file():
        """
        Read the config file in json format
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        # These default settings will be modified when the configuration
        # file is read. Keep the keys in sync with the default configuration
        # file.
        defaults = {}
        defaults['prte_path'] = [os.path.join(os.sep, 'opt', 'prte', 'bin'),
                                 os.path.join(os.sep, 'usr', 'bin')]
        defaults['prte_args'] = []
        defaults['prte_lock_file'] = os.path.join(PBS_MOM_HOME, 'mom_priv',
                                                  prte.lock)
        # Identify the config file and read in the data
        config_file = ''
        if 'PBS_PRTE_CONFIG_FILE' in os.environ:
            config_file = os.environ['PBS_PRTE_CONFIG_FILE']
        if not config_file:
            tmpcfg = os.path.join(PBS_MOM_HOME, 'mom_priv', 'hooks',
                                  'pbs_prte.CF')
            if os.path.isfile(tmpcfg):
                config_file = tmpcfg
        if not config_file:
            raise ProcessingError('Config file not found')
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Config file is %s' %
                   (caller_name(), config_file))
        pbs.logmsg(pbs.EVENT_DEBUG4,
                   '%s: prte hook configuration: %s' %
                   (caller_name(), config))
        return config

    def event_name(self, hooktype):
        """
        Return the event name for the supplied hook type.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        if hooktype in self.hook_events:
            return self.hook_events[hooktype]['name']
        pbs.logmsg(pbs.EVENT_DEBUG4,
                   '%s: Type: %s not found' % (caller_name(), type))
        return None

    def hashandler(self, hooktype):
        """
        Return the handler for the supplied hook type.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        if hooktype in self.hook_events:
            return self.hook_events[hooktype]['handler'] is not None
        return None

    def invoke_handler(self, event, jobutil, *args):
        """
        Call the appropriate handler for the supplied event.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: UID: real=%d, effective=%d' %
                   (caller_name(), os.getuid(), os.geteuid()))
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: GID: real=%d, effective=%d' %
                   (caller_name(), os.getgid(), os.getegid()))
        if self.hashandler(event.type):
            return self.hook_events[event.type]['handler'](event, jobutil,
                                                           *args)
        pbs.logmsg(pbs.EVENT_DEBUG2,
                   '%s: %s event not handled by this hook' %
                   (caller_name(), self.event_name(event.type)))
        return False

    def _execjob_begin_handler(self, event, jobutil):
        """
        Handler for execjob_begin events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Host assigned job resources: %s' %
                   (caller_name(), jobutil.assigned_resources))
        return True

    def _execjob_epilogue_handler(self, event, jobutil):
        """
        Handler for execjob_epilogue events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        return True

    def _execjob_end_handler(self, event, jobutil):
        """
        Handler for execjob_end events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        return True

    def _execjob_launch_handler(self, event, jobutil):
        """
        Handler for execjob_launch events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        # Create the rendezvous file
        # Launch prted
        # Set the PRRTE environment variables
        env_list = []
        env_list.append('PMIX_FOO=%s' % 'BAR')
        pbs.logmsg(pbs.EVENT_DEBUG4, 'ENV_LIST: %s' % env_list)
        return True

    def _exechost_periodic_handler(self, event, jobutil):
        """
        Handler for exechost_periodic events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        return True

    def _exechost_startup_handler(self, event, jobutil):
        """
        Handler for exechost_startup events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        return True

    def _execjob_attach_handler(self, event, jobutil):
        """
        Handler for execjob_attach events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        return True

    def _execjob_resize_handler(self, event, jobutil):
        """
        Handler for execjob_resize events.
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        return True

    def _execjob_postsuspend_handler(self, event, jobutil):
        """
        Handler for execjob_postsuspend events.
        """
        return True

    def _execjob_preresume_handler(self, event, jobutil):
        """
        Handler for execjob_preresume events.
        """
        return True


#
# CLASS JobUtils
#
class JobUtils(object):
    """
    Job utility methods
    """

    def __init__(self, job, hostname=None, assigned_resources=None):
        self.job = job
        if hostname is not None:
            self.hostname = hostname
        else:
            self.hostname = pbs.get_local_nodename()
        if assigned_resources is not None:
            self.assigned_resources = assigned_resources
        else:
            self.assigned_resources = self._get_assigned_job_resources()

    def __repr__(self):
        return ('JobUtils(%s, %s, %s)' %
                (repr(self.job),
                 repr(self.hostname),
                 repr(self.assigned_resources)))

    def write_to_stderr(self, job, msg):
        """
        Write a message to the job stderr file
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        try:
            filename = job.stderr_file()
            if filename is None:
                return
            with open(filename, 'a') as desc:
                desc.write(msg)
        except Exception:
            pass

    def setup_job_prte_env(self, gpus):
        """
        Setup the job environment for the devices assigned to the job for an
        execjob_launch hook
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        if 'devices' in self.subsystems:
            # prevent using GPUs without user awareness
            pbs.event().env['CUDA_VISIBLE_DEVICES'] = ''
        if 'device_names' in self.assigned_resources:
            names = self.assigned_resources['device_names']
            pbs.logmsg(pbs.EVENT_DEBUG4,
                       'devices: %s' % (names))
            offload_devices = []
            cuda_visible_devices = []
            for name in names:
                if name.startswith('mic'):
                    offload_devices.append(name[3:])
                elif name.startswith('nvidia'):
                    cuda_visible_devices.append(gpus[name]['uuid'])
            if offload_devices:
                value = "\\,".join(offload_devices)
                pbs.event().env['OFFLOAD_DEVICES'] = '%s' % value
                pbs.logmsg(pbs.EVENT_DEBUG4,
                           'offload_devices: %s' % offload_devices)
            if cuda_visible_devices:
                value = "\\,".join(cuda_visible_devices)
                pbs.event().env['CUDA_VISIBLE_DEVICES'] = '%s' % value
                pbs.event().env['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
                pbs.logmsg(pbs.EVENT_DEBUG4,
                           'cuda_visible_devices: %s' % cuda_visible_devices)
            pbs.logmsg(pbs.EVENT_DEBUG4,
                       'Environment: %s' % pbs.event().env)
            return [offload_devices, cuda_visible_devices]
        else:
            return False

    def write_job_env_file(self, jobid, env_list):
        """
        Write out host PMIx environment for this job
        """
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Method called' % caller_name())
        jobid = str(jobid)
        if not os.path.exists(self.host_job_env_dir):
            os.makedirs(self.host_job_env_dir, 0o755)
        # Write out assigned_resources
        try:
            lines = "\n".join(env_list)
            filename = self.host_job_env_filename % jobid
            with open(filename, 'w') as desc:
                desc.write(lines)
            pbs.logmsg(pbs.EVENT_DEBUG4, 'Wrote out file: %s' % (filename))
            pbs.logmsg(pbs.EVENT_DEBUG4, 'Data: %s' % (lines))
            return True
        except Exception:
            return False


def set_global_vars():
    """
    Define some global variables that the hook may use
    """
    global PBS_EXEC
    global PBS_HOME
    global PBS_MOM_HOME
    global PBS_MOM_JOBS
    # Determine location of PBS_HOME, PBS_MOM_HOME, and PBS_EXEC. These
    # should have each be initialized to empty strings near the beginning
    # of this hook.
    # Try the environment first
    if not PBS_EXEC and 'PBS_EXEC' in os.environ:
        PBS_EXEC = os.environ['PBS_EXEC']
    if not PBS_HOME and 'PBS_HOME' in os.environ:
        PBS_HOME = os.environ['PBS_HOME']
    if not PBS_MOM_HOME and 'PBS_MOM_HOME' in os.environ:
        PBS_MOM_HOME = os.environ['PBS_MOM_HOME']
    # Try the built in config values next
    pbs_conf = pbs.get_pbs_conf()
    if pbs_conf:
        if not PBS_EXEC and 'PBS_EXEC' in pbs_conf:
            PBS_EXEC = pbs_conf['PBS_EXEC']
        if not PBS_HOME and 'PBS_HOME' in pbs_conf:
            PBS_HOME = pbs_conf['PBS_HOME']
        if not PBS_MOM_HOME and 'PBS_MOM_HOME' in pbs_conf:
            PBS_MOM_HOME = pbs_conf['PBS_MOM_HOME']
    # Try reading the config file directly
    if not PBS_EXEC or not PBS_HOME or not PBS_MOM_HOME:
        if 'PBS_CONF_FILE' in os.environ:
            pbs_conf_file = os.environ['PBS_CONF_FILE']
        else:
            pbs_conf_file = os.path.join(os.sep, 'etc', 'pbs.conf')
        regex = re.compile(r'\s*([^\s]+)\s*=\s*([^\s]+)\s*')
        try:
            with open(pbs_conf_file, 'r') as desc:
                for line in desc:
                    match = regex.match(line)
                    if match:
                        if not PBS_EXEC and match.group(1) == 'PBS_EXEC':
                            PBS_EXEC = match.group(2)
                        if not PBS_HOME and match.group(1) == 'PBS_HOME':
                            PBS_HOME = match.group(2)
                        if not PBS_MOM_HOME and (match.group(1) ==
                                                 'PBS_MOM_HOME'):
                            PBS_MOM_HOME = match.group(2)
        except Exception:
            pass
    # If PBS_MOM_HOME is not set, use the PBS_HOME value
    if not PBS_MOM_HOME:
        PBS_MOM_HOME = PBS_HOME
    PBS_MOM_JOBS = os.path.join(PBS_MOM_HOME, 'mom_priv', 'jobs')
    # Sanity check to make sure each global path is set
    if not PBS_EXEC:
        raise ConfigError('Unable to determine PBS_EXEC')
    if not PBS_HOME:
        raise ConfigError('Unable to determine PBS_HOME')
    if not PBS_MOM_HOME:
        raise ConfigError('Unable to determine PBS_MOM_HOME')


#
# FUNCTION main
#
def main():
    """
    Main function for execution
    """
    pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Function called' % caller_name())
    # If an exception occurs, jobutil must be set to something
    jobutil = None
    hostname = pbs.get_local_nodename()
    pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Host is %s' % (caller_name(), hostname))
    # Log the hook event type
    event = pbs.event()
    pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Hook name is %s' %
               (caller_name(), event.hook_name))
    try:
        set_global_vars()
    except Exception:
        pbs.logmsg(pbs.EVENT_DEBUG,
                   '%s: Hook failed to initialize configuration properly' %
                   caller_name())
        pbs.logmsg(pbs.EVENT_DEBUG,
                   str(traceback.format_exc().strip().splitlines()))
        event.accept()
    # Instantiate the hook utility class
    try:
        hooks = HookUtils()
        pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Hook utility class instantiated' %
                   caller_name())
    except Exception:
        pbs.logmsg(pbs.EVENT_DEBUG,
                   '%s: Failed to instantiate hook utility class' %
                   caller_name())
        pbs.logmsg(pbs.EVENT_DEBUG,
                   str(traceback.format_exc().strip().splitlines()))
        event.accept()
    # Bail out if there is no handler for this event
    if not hooks.hashandler(event.type):
        pbs.logmsg(pbs.EVENT_DEBUG, '%s: %s event not handled by this hook' %
                   (caller_name(), hooks.event_name(event.type)))
        event.accept()
    try:
        # Instantiate the job utility class first so jobutil can be accessed
        # by the exception handlers.
        if hasattr(event, 'job'):
            jobutil = JobUtils(event.job)
            pbs.logmsg(pbs.EVENT_DEBUG4,
                       '%s: Job information class instantiated' %
                       caller_name())
        else:
            pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Event does not include a job' %
                       caller_name())
        # Parse the configuration file here so we can use the file lock
        cfg = HookUtils.parse_config_file()
        vnode = None
        if hasattr(event, 'vnode_list'):
            if hostname in event.vnode_list:
                vnode = event.vnode_list[hostname]
        with Lock(cfg['prte_lock_file']):
            # Only write this once we grabbed the lock,
            # otherwise *another* event could actually win the lock
            # even though *this* event printed this message last,
            # and we wouldd be confused about the event that the
            # winner services
            pbs.logmsg(pbs.EVENT_DEBUG4, '%s: Event type is %s' %
                       (caller_name(), hooks.event_name(event.type)))
            # Call the appropriate handler
            if hooks.invoke_handler(event, jobutil):
                pbs.logmsg(pbs.EVENT_DEBUG4,
                           '%s: Hook handler returned success for %s event' %
                           (caller_name(), hooks.event_name(event.type)))
                event.accept()
            else:
                pbs.logmsg(pbs.EVENT_DEBUG,
                           '%s: Hook handler returned failure for %s event' %
                           (caller_name(), hooks.event_name(event.type)))
                event.reject()
    except SystemExit:
        # The event.accept() and event.reject() methods generate a SystemExit
        # exception.
        pass
    except UserError as exc:
        # User must correct problem and resubmit job, job gets deleted
        msg = ('User error in %s handling %s event' %
               (event.hook_name, hooks.event_name(event.type)))
        if jobutil is not None:
            msg += (' for job %s' % (event.job.id))
            try:
                event.job.delete()
                msg += ' (deleted)'
            except Exception:
                msg += ' (deletion failed)'
        msg += (': %s %s' % (exc.__class__.__name__, str(exc.args)))
        pbs.logmsg(pbs.EVENT_ERROR, msg)
        event.reject(msg)
    except ProcessingError as exc:
        # Something went wrong processing the request
        pbs.logmsg(pbs.EVENT_DEBUG,
                   str(traceback.format_exc().strip().splitlines()))
        msg = ('Processing error in %s handling %s event' %
               (event.hook_name, hooks.event_name(event.type)))
        if jobutil is not None:
            msg += (' for job %s' % (event.job.id))
        msg += (': %s %s' % (exc.__class__.__name__, str(exc.args)))
        pbs.logmsg(pbs.EVENT_ERROR, msg)
        event.reject(msg)
    except Exception as exc:
        # Catch all other exceptions and report them, job gets held
        # and a stack trace is logged
        pbs.logmsg(pbs.EVENT_DEBUG,
                   str(traceback.format_exc().strip().splitlines()))
        msg = ('Unexpected error in %s handling %s event' %
               (event.hook_name, hooks.event_name(event.type)))
        if jobutil is not None:
            msg += (' for job %s' % (event.job.id))
            try:
                event.job.Hold_Types = pbs.hold_types('s')
                event.job.rerun()
                msg += ' (system hold set)'
            except Exception:
                msg += ' (system hold failed)'
        msg += (': %s %s' % (exc.__class__.__name__, str(exc.args)))
        pbs.logmsg(pbs.EVENT_ERROR, msg)
        event.reject(msg)


# The following block is skipped if this is a unit testing environment.
if (__name__ == 'builtins') or (__name__ == '__builtin__'):
    START = time.time()
    try:
        main()
    except SystemExit:
        # The event.accept() and event.reject() methods generate a
        # SystemExit exception.
        pass
    except Exception:
        # "Should never happen" since main() is supposed to catch these
        pbs.logmsg(pbs.EVENT_DEBUG,
                   str(traceback.format_exc().strip().splitlines()))
        pbs.event().reject(str(traceback.format_exc().strip().splitlines()))
    finally:
        pbs.logmsg(pbs.EVENT_DEBUG, 'Hook ended: %s, '
                   'event_type %s (elapsed time: %0.4lf)' %
                   (pbs.event().hook_name,
                    str(pbs.event().type),
                    (time.time() - START)))
