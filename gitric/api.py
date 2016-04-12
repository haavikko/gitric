from __future__ import with_statement

import os

from fabric.state import env
from fabric.api import (local, run, sudo, abort, task, cd, puts, require)
from fabric.context_managers import settings
from fabric.contrib.files import exists
from fabric.colors import green


def _do(use_sudo=False, sudo_user=None):
    # helper for using either sudo or
    def _inner(cmd, *args, **kw):
        if use_sudo:
            return sudo(cmd, user=sudo_user, *args, **kw)
        else:
            return run(cmd, *args, **kw)
    return _inner

@task
def allow_dirty():
    """ allow pushing even when the working copy is dirty """
    env.gitric_allow_dirty = True


@task
def force_push():
    """ allow pushing even when history will be lost """
    env.gitric_force_push = True

def git_init(repo_path, use_sudo=False, sudo_user=None):
    """ create a git repository if necessary [remote] """

    do = _do(use_sudo, sudo_user)

    def _config():
        do('git config receive.denyCurrentBranch ignore')

    # check if it is a git repository yet
    if exists('%s/.git' % repo_path, use_sudo=use_sudo):
        _config()
        return
    puts(green('Creating new git repository ') + repo_path)

    # create repository folder if necessary
    do('mkdir -p %s' % repo_path, quiet=True)

    with cd(repo_path):
        # initialize the remote repository
        do('git init')

        # silence git complaints about pushes coming in on the current branch
        # the pushes only seed the immutable object store and do not modify the
        # working copy
        _config()

def git_current_branch_name():
    return local('git rev-parse --abbrev-ref HEAD', capture=True)

def git_seed(repo_path,
             commit=None,
             remote_branch=None,
             ignore_untracked_files=False,
             use_sudo=False,
             sudo_user=None,
             remote_git_user=None):
    """ seed a git repository (and create if necessary) [remote] """

    # check if the local repository is dirty
    dirty_working_copy = git_is_dirty(ignore_untracked_files)
    if dirty_working_copy:
        abort(
            'Working copy is dirty. This check can be overridden by\n'
            'importing gitric.api.allow_dirty and adding allow_dirty to your '
            'call.')

    # check if the remote repository exists and create it if necessary
    git_init(repo_path, use_sudo=use_sudo, sudo_user=sudo_user)

    # use specified commit or HEAD
    commit = commit or git_head_rev()
    if not remote_branch:
        remote_branch = git_current_branch_name()
        if '* {}'.format(remote_branch) not in local('git branch --contains {}'.format(commit), capture=True):
            abort('Can not push: commit {} is not in branch {}'.format(commit, remote_branch))

    remote_git_user = remote_git_user or sudo_user or env.user

    # push the commit to the remote repository
    #
    # (note that pushing to the master branch will not change the contents
    # of the working directory)

    puts(green('Pushing commit ') + commit)
    puts(green('Pushing to remote branch ') + remote_branch)

    with settings(warn_only=True):
        force = ('gitric_force_push' in env) and '-f' or ''
        push = local(
            'git push git+ssh://%s@%s:%s%s %s:refs/heads/%s %s' % (
                remote_git_user, env.host, env.port, repo_path, commit, remote_branch, force))

    if push.failed:
        abort(
            '%s is a non-fast-forward\n'
            'push. The seed will abort so you don\'t lose information. '
            'If you are doing this\nintentionally import '
            'gitric.api.force_push and add it to your call.' % commit)


def git_reset(repo_path, commit=None, use_sudo=False, sudo_user=None):
    """ reset the working directory to a specific commit [remote] """
    do = _do(use_sudo, sudo_user)

    # use specified commit or HEAD
    commit = commit or git_head_rev()

    puts(green('Resetting to commit ') + commit)

    # reset the repository and working directory
    with cd(repo_path):
        do('git reset --hard %s' % commit)


def git_head_rev():
    """ find the commit that is currently checked out [local] """
    return local('git rev-parse HEAD', capture=True)


def git_is_dirty(ignore_untracked_files):
    """ check if there are modifications in the repository [local] """

    if 'gitric_allow_dirty' in env:
        return False

    untracked_files = '--untracked-files=no' if ignore_untracked_files else ''
    return local('git status %s --porcelain' % untracked_files,
                 capture=True) != ''


def init_bluegreen():
    require('bluegreen_root', 'bluegreen_ports')
    env.green_path = os.path.join(env.bluegreen_root, 'green')
    env.blue_path = os.path.join(env.bluegreen_root, 'blue')
    env.next_path_abs = os.path.join(env.bluegreen_root, 'next')
    env.live_path_abs = os.path.join(env.bluegreen_root, 'live')
    run('mkdir -p %(bluegreen_root)s %(blue_path)s %(green_path)s '
        '%(blue_path)s/etc %(green_path)s/etc' % env)
    if not exists(env.live_path_abs):
        run('ln -s %(blue_path)s %(live_path_abs)s' % env)
    if not exists(env.next_path_abs):
        run('ln -s %(green_path)s %(next_path_abs)s' % env)
    env.next_path = run('readlink -f %(next_path_abs)s' % env)
    env.live_path = run('readlink -f %(live_path_abs)s' % env)
    env.virtualenv_path = os.path.join(env.next_path, 'env')
    env.pidfile = os.path.join(env.next_path, 'etc', 'app.pid')
    env.nginx_conf = os.path.join(env.next_path, 'etc', 'nginx.conf')
    env.color = os.path.basename(env.next_path)
    env.bluegreen_port = env.bluegreen_ports.get(env.color)


def swap_bluegreen():
    require('next_path', 'live_path', 'live_path_abs', 'next_path_abs')
    run('ln -nsf %(next_path)s %(live_path_abs)s' % env)
    run('ln -nsf %(live_path)s %(next_path_abs)s' % env)
