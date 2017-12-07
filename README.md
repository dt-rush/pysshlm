pysshlm
===

## why?

This program was created to wrap an ssh session with the ability to enter a hotkey which pops you out into "line-editing mode", so that you can type full lines without sending a single char at a time over the tunnel and waiting for it to ACK. This can really be an annoyance especially if your keyboard, like mine, misses keys sometimes, and *especially* you're on a very high latency link, such as a GSM or satellite link.

It is inspired by [ssh-line-mode](https://github.com/mnalis/ssh-line-mode/), written in Perl. I had issues installing and running it on a server where I'm restricted to being a user and can't install system packages, so I decided rather than dive into local installation of Perl with my hands tied behind my back, I'd make use of the freedom afforded by the sysadmins providing a python2.7 interpeter in the environment.

## contributors

dt-rush <nick.8.payne@gmail.com>
