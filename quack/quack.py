#!/usr/bin/env python
# pylint: disable=C0325,W0603

"""Quack!!"""

import argparse
import git
import os
import shutil
import subprocess
import sys
import textwrap
import yaml


_ARGS = None

class Module(object):

    """A container for module metadata."""

    def __init__(
            self, name, repository,
            path='', branch='master', hexsha=None, tag=None, isfile=False):
        """Initialise a new `Module` object.

        :param str name: the name of the module
        :param str repository: the URI for the repository to clone
        :param str path: the path to clone the repository into. Default
        :param str branch: the branch name to checkout. Default: master
        :param str hexsha: the SHA of the commit to checkout. Mutually exclusive
            with `tag`.
        :param str tab: the tag of the commit to checkout. Mutually exclusive
            with `hexsha`.
        :param bool isfile:
        """
        self.name = name
        self.repository = repository
        self.path = path
        self.branch = branch
        self.hexsha = hexsha
        self.tag = tag
        self.isfile = isfile

    @staticmethod
    def from_config(name, config):
        """Generate a `Module` instance from a configuration dictionary.

        :param str name: the name of the module
        :param dict config: the configuration as read from the YAML file
        """
        try:
            config['repository']
        except KeyError:
            sys.stderr.write("Module does not specify a 'repository'\n")
            sys.exit(1)
        return Module(name, **config)


def _setup():
    """Setup parser if executed script directly."""
    parser = argparse.ArgumentParser(
        description='Quack builder',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-y', '--yaml', default='quack.yaml', help='Provide custom yaml')
    parser.add_argument(
        '-p', '--profile', default='init', help='Run selected profile',
        nargs='?')
    return parser.parse_args()


def _remove_dir(directory):
    """Remove directory."""
    if os.path.exists(directory):
        shutil.rmtree(directory)
        return True
    return False


def _create_dir(directory):
    """Create directory."""
    if not os.path.exists(directory):
        os.makedirs(directory)


def _get_config():
    """Return yaml configuration."""
    yaml_file = (hasattr(_ARGS, 'yaml') and _ARGS.yaml)
    if os.path.isfile(yaml_file):
        with open(yaml_file) as file_pointer:
            return yaml.load(file_pointer)
    return


def _iter_modules(config):
    """Iterate `Module` objects as defined by `config`.

    :type config: dict
    """
    module_list = config.get('modules', {})
    for name, config in module_list.items():
        yield Module.from_config(name, config)


def _nice_call(command, **popenkwargs):
    """Thin wrapper around `subprocess.Popen`, with nicer logging.

    :param str command: the entire command to execute
    :param popenkwargs: arguments to pass to `subprocess.Popen`
    """
    workdir = popenkwargs.get('cwd', os.getcwd())
    print("Executing %r in %s..." % (command, workdir))
    p = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popenkwargs)
    ret = p.wait()
    stdout, stderr = p.communicate()
    if ret == 0:
        print("Got stdout:\n%s" % stdout)
    else:
        sys.stderr.write("Command failed with status %d, stderr=\n%s" % stderr)
        sys.exit(1)


def _fetch_modules(config, specific_module=None):
    """Fetch git submodules."""
    module_list = config.get('modules')
    if not module_list:
        print('No modules found.')
        return
    modules = '.quack/modules'
    ignore_list = []
    _remove_dir('.git/modules/')
    _create_dir(modules)
    if config.get('gitignore') and os.path.isfile('.gitignore'):
        with open('.gitignore', 'r') as file_pointer:
            ignore_list = list(set(file_pointer.read().split('\n')))
    repo = git.Repo('.')
    for module in _iter_modules(config):
        if specific_module and specific_module != module.name:
            continue
        if module.tag and module.hexsha:
            print('%s: Cannot be both tag & hexsha.' % module.name)
            continue
        print('Cloning: ' + module.repository)
        sub_module = repo.create_submodule(
            module.name, modules + '/' + module.name,
            url=module.repository,
            branch=module.branch
        )

        if module.tag:
            _nice_call(
                'git checkout --quiet tags/%s' % tag,
                cwd=modules + '/' + module.name)
            checkout_target = module.tag
        elif module.hexsha:
            _nice_call(
                'git checkout --quiet %s' % hexsha,
                cwd=modules + '/' + module.name)
            checkout_target = module.hexsha
        else:
            checkout_target = sub_module.hexsha

        from_path = '%s/%s/%s' % (modules, module.name, module.path)
        is_exists = os.path.exists(from_path)
        if (module.path and is_exists) or not module.path:
            if module.isfile:
                if os.path.isfile(module.name):
                    os.remove(module.name)
                shutil.copyfile(from_path, module.name)
            else:
                _remove_dir(module.name)
                shutil.copytree(
                    from_path, module.name,
                    ignore=shutil.ignore_patterns('.git*'))
        elif not is_exists:
            print('%s folder does not exists. Skipped.' % module.path)

        # Remove submodule.
        sub_module.remove()
        if os.path.isfile('.gitmodules'):
            _nice_call('rm .gitmodules')
            _nice_call('git rm --quiet --cached .gitmodules')

        print('Cloned: %s (%s)' % (module.name, checkout_target))

        if config.get('gitignore'):
            with open('.gitignore', 'a') as file_pointer:
                if module.name not in ignore_list:
                    file_pointer.write('\n' + module.name)
                    ignore_list.append(module.name)


def _clean_modules(config, specific_module=None):
    """Remove all given modules."""
    for module in config.get('modules').items():
        if specific_module and specific_module != module[0]:
            continue
        if _remove_dir(module[0]):
            print('Cleaned', module[0])


def _run_nested_quack(dependency):
    """Execute all required dependencies."""
    if not dependency or dependency[0] != 'quack':
        return
    quack = dependency[1]
    slash_index = quack.rfind('/')
    command = ['quack']
    module = os.getcwd()
    if slash_index > 0:
        module = quack[:slash_index]
    colon_index = quack.find(':')
    if len(quack) > colon_index + 1:
        command.append('-p')
        command.append(quack[colon_index + 1: len(quack)])
    if colon_index > 0:
        command.append('-y')
        command.append(quack[slash_index + 1:colon_index])
    print('Quack..' + module)
    git.Repo.init(module)
    _create_dir(module)
    _nice_call(' '.join(command), cwd=module)
    _remove_dir(module + '/.git')
    return True


def _run_tasks(config, profile):
    """Run given tasks."""
    dependencies = profile.get('dependencies', {})
    stats = {'tasks': 0, 'dependencies': 0}
    if isinstance(dependencies, dict):
        for dependency in profile.get('dependencies', {}).items():
            _run_nested_quack(dependency)
            stats['dependencies'] += 1
    tasks = profile.get('tasks', [])
    if not tasks:
        print('No tasks found.')
        return stats
    for command in tasks:
        stats['tasks'] += 1
        is_negate = command[0] == '-'
        if is_negate:
            command = command[1:]
        module = None
        is_modules = command.find('modules:') == 0 or 'modules' == command
        is_quack = command.find('quack:') == 0
        is_cmd = command.find('cmd:') == 0

        if is_modules and command != 'modules':
            module = command.replace('modules:', '')
        elif is_quack:
            _run_nested_quack(('quack', command.replace('quack:', '')))
        elif is_cmd:
            cmd = command.replace('cmd:', '')
            _nice_call(cmd)

        if is_modules and not is_negate:
            _fetch_modules(config, module)
        elif is_modules and is_negate:
            _clean_modules(config, module)
    return stats


def _prompt_to_create():
    """Prompt user to create quack configuration."""
    pyversion = sys.version_info.major
    prompt = input
    if pyversion < 3:
        prompt = raw_input
    yes_or_no = prompt(
        'No quack configuration found, do you want to create one? (y/N): ')
    if yes_or_no.lower() == 'y':
        project_name = prompt('Provide project name: ')
        with open('quack.yaml', 'a') as file_pointer:
            file_pointer.write(textwrap.dedent("""
                name: %s
                modules:
                profiles:
                  init:
                    tasks: ['modules']
                """ % project_name).strip())
        return _get_config()
    return


def main():
    """Entry point."""
    global _ARGS
    _create_dir('.quack')
    if _ARGS is None:
        _ARGS = _setup()
    config = _get_config()
    if not config:
        config = _prompt_to_create()
        if not config:
            return
    profile = config.get('profiles', {}).get(_ARGS.profile, {})
    # print(_ARGS.profile, profile)
    stats = _run_tasks(config, profile)
    print('%s task(s) completed with %s dependencies.' % (
        stats['tasks'], stats['dependencies']))

if __name__ == '__main__':
    _ARGS = _setup()
    main()
