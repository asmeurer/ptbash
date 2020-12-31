import sys

from pexpect import spawn, EOF
from prompt_toolkit import PromptSession

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

    while expect_prompt(): # retcode := bash.poll() is not None:
        try:
            print(bash.before.decode('utf-8'), end='')
            command = session.prompt("$ ")
            bash.send(command.encode('utf-8') + b'\n')
        except EOFError:
            bash.sendeof()
    sys.exit(bash.exitstatus)

if __name__ == '__main__':
    run()
