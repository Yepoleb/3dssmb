#!/usr/bin/env python3

import logging
import cmd
import ntpath
import os
import shlex
import getpass
import argparse
import inspect

from smb.smb_structs import OperationFailure
from smb.SMBConnection import SMBConnection
from nmb.NetBIOS import NetBIOS


DEFAULT_TIMEOUT = 5
DEFAULT_PORT = 139
DEFAULT_SERVICE = "microSD"
DEFAULT_CLIENTNAME = "3DSCLIENT"


def complete_config(config):
    if config["servername"] is None:
        config["servername"] = input("3DS Name: ")
    if config["username"] is None:
        config["username"] = input("Username: ")
    if config["password"] is None:
        config["password"] = getpass.getpass()
    if config["serverip"] is None:
        nb_conn = NetBIOS()
        query_ips = nb_conn.queryName(config["servername"],
            timeout=DEFAULT_TIMEOUT)
        nb_conn.close()
        if not query_ips or len(query_ips) > 1:
            print("[Error] Name resolution failed. "
                "Please enter the 3DS IP manually.")
            config["serverip"] = input("IP: ")
        elif len(query_ips) == 1:
            config["serverip"] = query_ips[0]
    if config["serverport"] is None:
        config["serverport"] = DEFAULT_PORT
    if config["service"] is None:
        config["service"] = DEFAULT_SERVICE

    return config

def format_size(num, suffix="B"):
    """
    Credit: Fred Cirera, http://stackoverflow.com/a/1094933
    """
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0

def print_filelist(filelist):
    # Sort directories first and by file name
    filelist.sort(key=lambda f: (not f[1], f[0].lower()))
    max_sizelen = max(len(f[2]) for f in filelist)

    for filename, isdir, size in filelist:
        if filename in (".", ".."):
            continue
        print("{:>{w}} {}".format(size, filename, w=max_sizelen))



class ClientCmd(cmd.Cmd):
    prompt = "> "

    def __init__(self, config, completekey="tab", stdin=None, stdout=None):
        super().__init__(completekey, stdin, stdout)
        self.conn = None
        self._connect(config)

    def do_ls(self, arg_str):
        """
        ls [directory]

        Lists the contents of a remote directory. Defaults to the current one.
        """
        args = shlex.split(arg_str)
        if not args:
            path = self.cur_dir
        elif len(args) == 1:
            path = self._path_for(args[0])
        else:
            print("Too many arguments")
            return

        resp = self.conn.listPath(self.service, path)
        filelist = []
        for sf in resp:
            if sf.isDirectory:
                filelist.append((sf.filename, True, "-"))
            else:
                filelist.append((sf.filename, False,
                    format_size(sf.file_size)))

        print_filelist(filelist)

    def do_lls(self, arg_str):
        """
        lls [directory]

        Lists the contents of a local directory. Defaults to the current one.
        """
        args = shlex.split(arg_str)
        if not args:
            path = os.getcwd()
        elif len(args) == 1:
            path = self._lpath_for(args[0])
        else:
            print("Too many arguments")
            return

        filelist = []
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            if os.path.isdir(filepath):
                filelist.append((filename, True, "-"))
            else:
                filelist.append((filename, False,
                    format_size(os.path.getsize(filepath))))

        print_filelist(filelist)

    def do_mkdir(self, arg_str):
        """
        mkdir <directory>

        Creates a new directory.
        """
        args = shlex.split(arg_str)
        if not args:
            print("Error: Directory name is missing")
            return

        for arg in args:
            self.conn.createDirectory(self.service, self._path_for(arg))

    def do_cd(self, arg_str):
        """
        cd <director>

        Changes the current remote working directory.
        """
        args = shlex.split(arg_str)
        if not args:
            path = "\\"
        elif len(args) == 1:
            path = self._path_for(args[0])
        else:
            print("[Error] Too many arguments")
            return
        self._change_dir(path)

    def do_lcd(self, arg_str):
        """
        lcd <director>

        Changes the current local working directory.
        """
        args = shlex.split(arg_str)
        if not args:
            path = self._lpath_for("~")
        elif len(args) == 1:
            path = self._lpath_for(args[0])
        else:
            print("[Error] Too many arguments")
            return

        os.chdir(path)

    def do_get(self, arg_str):
        """
        get <file> [dest]

        Downloads a file to the current local working directory or dest.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] File name is missing")
            return
        if len(args) == 1:
            src = self._path_for(args[0])
            dest = self._lpath_for(ntpath.basename(src))
        elif len(args) == 2:
            src = self._path_for(args[0])
            dest = self._lpath_for(args[1])
        else:
            print("[Error] Too many arguments")
            return

        with open(dest, "wb") as localfile:
            self.conn.retrieveFile(self.service, src, localfile)

    def do_mget(self, arg_str):
        """
        mget <files...>

        Downloads multiple files to the current local working directory.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] File name is missing")
            return

        for arg in args:
            filename = ntpath.basename(arg)
            print("Downloading", filename)
            src = self._path_for(arg)
            dest = self._lpath_for(filename)
            with open(dest, "wb") as localfile:
                self.conn.retrieveFile(self.service, src, localfile)

    def do_put(self, arg_str):
        """
        put <file> [dest]

        Uploads a file to the current remote working directory or dest.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] File name is missing")
            return
        if len(args) == 1:
            src = self._lpath_for(args[0])
            dest = self._path_for(os.path.basename(src))
        elif len(args) == 2:
            src = self._lpath_for(args[0])
            dest = self._path_for(args[1])
        else:
            print("[Error] Too many arguments")
            return

        with open(src, "rb") as localfile:
            self.conn.storeFile(self.service, dest, localfile)

    def do_mput(self, arg_str):
        """
        mput <files...>

        Uploads multiple files to the current remote working directory.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] File name is missing")
            return

        for arg in args:
            filename = os.path.basename(arg)
            print("Uploading", filename)
            src = self._lpath_for(arg)
            dest = self._path_for(filename)
            with open(src, "rb") as localfile:
                self.conn.storeFile(self.service, dest, localfile)

    def do_rm(self, arg_str):
        """
        rm <files...>

        Removes one or more files.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] File name is missing")
            return

        for arg in args:
            self.conn.deleteFiles(self.service, self._path_for(arg))

    def do_rmdir(self, arg):
        """
        rmdir <dirs...>

        Removes one or more directories.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] Directory name is missing")
            return

        for arg in args:
            self.conn.deleteDirectory(self.service, self._path_for(arg))

    def do_mv(self, arg_str):
        """
        mv <source> [sources...] <dest>

        Moves or renames a file.
        """
        args = shlex.split(arg_str)
        if not args:
            print("[Error] File name is missing")
            return
        elif len(args) == 1:
            print("[Error] New name is missing")
            return
        elif len(args) == 2:
            src = self._path_for(args[0])
            dest = self._path_for(args[1])
            self.conn.rename(self.service, src, dest)
        else:
            dest_dir = self._path_for(args[-1])
            for arg in args[:-1]:
                filename = ntpath.basename(arg)
                print("Moving", filename)
                src = self._path_for(arg)
                dest = ntpath.join(dest_dir, filename)
                self.conn.rename(self.service, src, dest)

    def do_pwd(self, arg_str):
        """
        pwd

        Prints the current working directories.
        """
        print("Remote:", self.cur_dir)
        print("Local:", os.getcwd())

    def do_info(self, arg_str):
        """
        info

        Shows details about the connection.
        """
        print("Capabilities:", hex(self.conn.capabilities))
        print("Security mode:", self.conn.security_mode)
        print("Max raw size:", self.conn.max_raw_size)
        print("Max buffer size:", self.conn.max_buffer_size)
        print("Max mpx count:", self.conn.max_mpx_count)
        print("Use plaintext auth:", self.conn.use_plaintext_authentication)

    def do_quit(self, arg_str):
        """
        quit

        Disconnect and close the program
        """
        return True

    # Aliases

    do_dir = do_ls
    do_ldir = do_lls
    do_del = do_rm
    do_delete = do_rm
    do_rename = do_mv
    do_q = do_quit
    do_exit = do_quit
    do_EOF = do_quit

    # Help

    def do_help(self, arg_str):
        """
        help [command]

        List available commands or detailed help on a specific command.
        """
        # Wrapper to handle docstrings according to PEP 257
        if arg_str and not hasattr(self, "help_" + arg_str):
            try:
                doc = getattr(self, "do_" + arg_str).__doc__
                if doc:
                    doc = inspect.cleandoc(str(doc))
                    self.stdout.write("%s\n" % doc)
                    return
            except AttributeError:
                pass

        super().do_help(arg_str)


    # Private methods

    def _connect(self, config):
        if self.conn is not None:
            self.conn.close()

        complete_config(config)

        self.conn = SMBConnection(
            username=config["username"],
            password=config["password"],
            my_name=DEFAULT_CLIENTNAME,
            remote_name=config["servername"],
            domain="",
            use_ntlm_v2=True,
            is_direct_tcp=False)

        self.conn.connect(config["serverip"], config["serverport"],
            timeout=DEFAULT_TIMEOUT)

        self.service = config["service"]
        self.cur_dir = "\\"

        print("Connected to", config["serverip"])

    def _path_for(self, path):
        return ntpath.normpath(ntpath.join(self.cur_dir, path))

    def _lpath_for(self, path):
        return os.path.join(os.getcwd(), os.path.expanduser(path))

    def _change_dir(self, path):
        try:
            self.conn.listPath(self.service, path)
            self.cur_dir = path
        except OperationFailure as e:
            print("[Error] Failed to change directory:", e.status.name)




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FTP-like client for managing 3DS microSD shares.")
    parser.add_argument("name", nargs="?", help="name of the 3DS")
    parser.add_argument("user", nargs="?")
    parser.add_argument("password", nargs="?")
    parser.add_argument("--ip", help="IP in case ")
    parser.add_argument("--port", type=int)
    parser.add_argument("-s", "--share",
        help="SMB share name. You should not need this.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    config = {
        "servername": args.name,
        "username": args.user,
        "password": args.password,
        "serverip": args.ip,
        "serverport": args.port,
        "service": args.share
    }

    client = ClientCmd(config)
    client.cmdloop()
