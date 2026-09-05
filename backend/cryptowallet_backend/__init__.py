import pymysql

# Django's "django.db.backends.mysql" engine expects the MySQLdb (mysqlclient)
# driver. PyMySQL is a pure-Python drop-in replacement that doesn't need a
# C compiler / system MySQL headers to install, so we tell it to pose as
# MySQLdb here -- this must happen before Django touches the database.
pymysql.install_as_MySQLdb()
pymysql.version_info = (1, 4, 6, 'final', 0)  # satisfies Django's version check
