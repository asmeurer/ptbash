import os
import sys
import subprocess
import threading
import time

from pexpect import spawn, EOF

from prompt_toolkit import PromptSession

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def run():
    # We need to connect bash to a pseudo-terminal to trick it into making the
    # output unbuffered.
    # TODO: Figure out how to pipe stdout and stderr.
    bash_args = ['--noediting', '--noprofile', '--norc']
    bash = spawn('bash', bash_args, env={})
    bash.setecho(False)
    default_bash_prompt = 'bash-3.2$ '

    session = PromptSession()
    def expect_prompt():
        res = bash.expect_exact([default_bash_prompt, EOF])
        return res == 0

    setup_git_prompt(session)
    while expect_prompt(): # retcode := bash.poll() is not None:
        try:
            print(bash.before.decode('utf-8'), end='')
            command = session.prompt(ps1())
            bash.send(command.encode('utf-8') + b'\n')
        except EOFError:
            bash.sendeof()
    sys.exit(bash.exitstatus)

def git_prompt():
    gitprompt = os.environ.get("GIT_PROMPT_FILE")
    if not gitprompt:
        return ''
    # Make sure these are exported so that they are inherited by ptbash.
    GIT_ENVS = {k: v for k, v in os.environ.items() if
                k.startswith("GIT_PS1")}
    p = subprocess.run(
        ['bash', '-c', f'source {gitprompt};echo $(__git_ps1)'],
        stdout=subprocess.PIPE, encoding='utf-8', env=GIT_ENVS)
    return p.stdout.strip()

def ps1():
    return git_prompt() + '$ '

def setup_git_prompt(session):
    # TODO: Handle being in a subdirectory
    git_dir = '.git'

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.src_path == os.path.abspath(os.path.join(git_dir, 'HEAD')):
                callback()
        on_created = on_modified

    def callback():
        session.message = ps1()
        session.app.invalidate()

    def watch():
        observer = Observer()
        observer.schedule(Handler(), git_dir)
        observer.start()
        try:
            while True:
                time.sleep(1)
        finally:
            observer.stop()
            observer.join()

    t = threading.Thread(target=watch)
    t.start()

if __name__ == '__main__':
    run()
