#!/usr/bin/env python3
import os
import sys
import subprocess
import warnings

import trio
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=trio.TrioDeprecationWarning)
    import trio_asyncio

import ptyprocess

from pygments.lexers.shell import BashLexer
from pygments.styles import get_style_by_name
from pygments.token import Token

from prompt_toolkit import PromptSession
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import style_from_pygments_cls
from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.named_commands import accept_line
from prompt_toolkit.filters import in_paste_mode

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

async def run():
    # We need to connect bash to a pseudo-terminal to trick it into making the
    # output unbuffered.
    # TODO: Figure out how to pipe stdout and stderr.
    bash_args = ['bash', '--noediting', '--noprofile', '--norc']
    env = os.environ.copy()
    env['PS1'] = ''

    key_bindings = KeyBindings()

    key_bindings.add('enter')(accept_line)

    @key_bindings.add(Keys.Escape, 'enter')
    def _newline(event):
        """
        Newline (in case of multiline input.
        """
        event.current_buffer.newline(copy_margin=not in_paste_mode())

    session = PromptSession(lexer=PygmentsLexer(BashLexer),
                            style=style_from_pygments_cls(get_style_by_name('monokai')),
                            multiline=True,
                            prompt_continuation=ps2(),
                            key_bindings=key_bindings)


    git_watcher = setup_git_prompt(session)

    try:
        process = ptyprocess.PtyProcess.spawn(bash_args, env=env, echo=False)
        iostream = trio.lowlevel.FdStream(process.fd)

        async def _write_stdout():
            with patch_stdout(raw=True):
                while True:
                    sys.stdout.write((await iostream.receive_some()).decode('utf-8'))
        # stderr = process.stderr
        # async def _write_stderr():
        #     sys.stderr.buffer.write(await stderr.receive_some())
        async def _write_stdin(receive_channel):
            async with receive_channel:
                while True:
                    async for value in receive_channel:
                        await iostream.send_all(value)
        async def _get_command(send_channel):
            async with send_channel:
                while True:
                    command = await trio_asyncio.aio_as_trio(session.prompt_async)(ps1())
                    await send_channel.send(command.encode('utf-8') + b'\n')
        try:
            async with trio.open_nursery() as nursery:
                send_channel, receive_channel = trio.open_memory_channel(0)
                nursery.start_soon(_write_stdout)
                nursery.start_soon(_get_command, send_channel)
                # nursery.start_soon(_write_stderr)
                nursery.start_soon(_write_stdin, receive_channel)
                nursery.start_soon(git_watcher)
        except EOFError:
            process.terminate()
    finally:
        process.terminate()
        sys.exit(process.exitstatus)

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

def ps2():
    return PygmentsTokens([(Token.Generic.Prompt, os.environ.get('PS2', '> '))])

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

    async def watch():
        observer = Observer()
        observer.schedule(Handler(), git_dir)
        observer.start()
        try:
            while True:
                await trio.sleep(1)
        finally:
            observer.stop()
            observer.join()

    return watch

if __name__ == '__main__':
    trio_asyncio.run(run)
