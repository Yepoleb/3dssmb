# 3DSSMB

FTP-like client for managing New Nintendo 3DS microSD shares.

# Usage

```
python3 3dssmb.py [name] [user] [password]
```

Example:
```
python3 3dssmb.py MY-3DS 3ds password
```

Or if you want to interactively enter the login credentials:

```
python3 3dssmb.py
```

CLI commands can be listed using the `help` command.

# Dependencies

* Custom fork of [pysmb]
* [pyasn1]

# License

* [MIT](LICENSE)

[pysmb]: https://github.com/Yepoleb/pysmb
[pyasn1]: http://pyasn1.sourceforge.net/

