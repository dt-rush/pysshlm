
from pysshlm.thin_wrapper import ThinWrapper


# entrypoint functionsd
def run_session (host):

    # build the wrapper
    w = ThinWrapper (['ssh', host])
    # enter the wrapper (spawns 2 threads to flow input and output, so is non-blocking)
    w.enter()


    
    
    
    
    
    
