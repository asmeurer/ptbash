import sys
from subprocess import Popen, PIPE

from prompt_toolkit import prompt

def run():
    # We need to connect bash to a pseudo-terminal to trick it into making the
    # output unbuffered.
    # TODO: Figure out how to pipe stdout and stderr.
    bash = Popen(['script', '-q', '/dev/null', 'bash', '--noediting',
                  '--noprofile', '--norc'], stdin=PIPE, env={})

    print("Starting loop")
    while True: # retcode := bash.poll() is not None:
        command = prompt("$ ")
        bash.stdin.write(command.encode('utf-8') + b'\n')
        bash.stdin.flush()
    sys.exit(retcode)

if __name__ == '__main__':
    run()
