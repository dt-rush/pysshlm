pysshlm
===

## why?

This program was created to wrap an ssh session with the ability to enter a hotkey which pops you out into "line-editing mode", so that you can type full lines without sending a single char at a time over the tunnel and waiting for it to ACK. This can really be an annoyance especially if your keyboard, like mine, misses keys sometimes, and *especially* you're on a very high latency link, such as a GSM or satellite link.

It is inspired by [ssh-line-mode](https://github.com/mnalis/ssh-line-mode/), written in Perl. I had issues installing and running it on a server where I'm restricted to being a user and can't install system packages, so I decided rather than dive into local installation of Perl with my hands tied behind my back, I'd make use of the freedom afforded by the sysadmins providing a python2.7 interpeter in the environment.

## how?

After installing (see INSTALL.md), run the command, optionally specifying a user and a password:

    pysshlm [user@]host [--password "wow you should really use keypairs"]

Once the session starts, you can type CTRL+L at any time to pop into and out of line-editing mode.

I hope to implement line history and arrow key line navigation (including CTRL+left, CTRL+right) soon. Tab completion doesn't work. It would be a massive annoyance to implement. Pop out of line-editing mode, get what you need, and dear god jump back into line-editing mode as fast as you can.

## windows

Windows is not supported and I can't believe you are trying to do terminal-based stuff in windows. I'm sorry to hear about that. Let me guess, you got the cygwin blues? Or is gitbash a harsh mistress? Maybe try VirtualBox? 

![Yep.](/images/linuxftw.gif?raw=true)

## contributors

dt-rush <nick.8.payne@gmail.com>
