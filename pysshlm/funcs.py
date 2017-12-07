
from pysshlm.thin_wrapper import ThinWrapper


# entrypoint functionsd
def run_session (ssharg, password=None):

    # build the wrapper
    w = ThinWrapper (['ssh', ssharg], password)
    # enter the wrapper (spawns 2 threads to flow input and output, so is non-blocking)
    w.enter()


    
    
    
    
    
    
