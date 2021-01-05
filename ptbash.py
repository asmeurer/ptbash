#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import time

import trio
import trio_asyncio

from pygments.lexers.shell import BashLexer
from pygments.styles import get_style_by_name
from pygments.token import Token

from prompt_toolkit import PromptSession
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import style_from_pygments_cls
from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.patch_stdout import patch_stdout

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

async def run():
    # We need to connect bash to a pseudo-terminal to trick it into making the
    # output unbuffered.
    # TODO: Figure out how to pipe stdout and stderr.
    bash_args = ['bash', '--noediting', '--noprofile', '--norc']
    env = os.environ.copy()
    env['PS1'] = ''

    session = PromptSession(lexer=PygmentsLexer(BashLexer),
                            style=style_from_pygments_cls(get_style_by_name('monokai')))


    setup_git_prompt(session)

    async with await trio.open_process(bash_args, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       env=env) as process:
        stdin = process.stdin
        stdout = process.stdout
        async def _write_stdout():
            with patch_stdout(raw=True):
                while True:
                    sys.stdout.write((await stdout.receive_some()).decode('utf-8'))
        # stderr = process.stderr
        # async def _write_stderr():
        #     sys.stderr.buffer.write(await stderr.receive_some())
        async def _write_stdin(receive_channel):
            async with receive_channel:
                while True:
                    async for value in receive_channel:
                        await stdin.send_all(value)
        async def _get_command(send_channel):
            async with send_channel:
                while True:
                    command = await trio_asyncio.aio_as_trio(session.prompt_async)(ps1())
                    await send_channel.send(command.encode('utf-8') + b'\n')
        try:
            async with trio.open_nursery() as nursery:
                send_channel, receive_channel = trio.open_memory_channel(0)
                # command = session.prompt(ps1())
                nursery.start_soon(_write_stdout)
                nursery.start_soon(_get_command, send_channel)
                # nursery.start_soon(_write_stderr)
                nursery.start_soon(_write_stdin, receive_channel)
        except EOFError:
            process.terminate()
    sys.exit(process.returncode)

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
    return PygmentsTokens([(Token.Generic.Strong, git_prompt()),
                           (Token.Generic.Prompt, '$ ')])

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
    trio_asyncio.run(run)
