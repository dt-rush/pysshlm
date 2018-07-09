pysshlm
===

[![Build Status](https://travis-ci.com/dt-rush/pysshlm.svg?branch=master)](https://travis-ci.com/dt-rush/pysshlm)

## why?

This program was created to wrap an ssh session with the ability to enter a hotkey which pops you out into "line-editing mode", so that you can type full lines without sending a single char at a time over the tunnel and waiting for it to ACK. This can really be an annoyance especially if your keyboard, like mine, misses keys sometimes, and *especially* you're on a very high latency link, such as a GSM or satellite link.

It is inspired by [ssh-line-mode](https://github.com/mnalis/ssh-line-mode/), written in Perl. I had issues installing and running it on a server where I'm restricted to being a user and can't install system packages, so I decided rather than dive into local installation of Perl with my hands tied behind my back, I'd make use of the freedom afforded by the sysadmins providing a python2.7 interpeter in the environment.

## installation

```
git clone https://github.com/dt-rush/pysshlm
cd pysshlm
python setup.py install
```
If you don't have root access on your box, run 
```
python setup.py install --user
```
... and be sure to add `$HOME/.local/bin` to your `PATH`.

## how to use

After installing, run the command, optionally specifying a user and a password:

    pysshlm [user@]host

Once the session starts, you can type CTRL+] at any time to pop into and out of line-editing mode.

You can force quit in line-mode by hitting CTRL+D.

## future features

* line history with up/down arrow keys 
* left/right arrow key line navigation (including CTRL+left, CTRL+right)
* tab completion (this will be a bit annoying to implement)
