#!/usr/bin/python

import errno
import gzip
import logging
import os
import psutil
import pycurl
import random
import re
import shutil
import signal
import tempfile
import time
import unidecode
import yaml

import smtplib
from email import encoders
from email.header import Header
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.utils import COMMASPACE, formatdate
from sonicprobe.libs import urisup

try:
    from StringIO import CStringIO as StringIO
except ImportError:
    from StringIO import StringIO

try:
    from yaml import CSafeLoader as YamlLoader, CDumper as YamlDumper
except ImportError:
    from yaml import SafeLoader as YamlLoader, Dumper as YamlDumper


BUFFER_SIZE = 1 << 16
LOG         = logging.getLogger('sonicprobe.helpers')

_alphanum   = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

def boolize(value):
    if isinstance(value, basestring):
        if not value.isdigit():
            return False
        value = int(value)

    return int(bool(value))

def is_scalar(value):
    """ Returns True if is scalar or False otherwise """
    return isinstance(value, (basestring, bool, int, long, float))

def is_print(value, space = True, tab = False, crlf = False):
    """ Returns True if is print or False otherwise """
    if not isinstance(value, basestring):
        return False

    regex = r'\x00-\x08\x0B\x0C\x0E-\x1F\x7F'

    if not space:
        regex += r'\x20'

    if tab:
        regex += r'\x09'

    if crlf:
        regex += r'\x0A\x0D'

    return re.match(r'[' + regex + ']', value, re.U) is None

def clean_string(value):
    if not is_print(value):
        return False

    return re.sub('\s\s+', ' ', value.strip())

def normalize_string(value, case = None):
    if not is_print(value):
        return False

    if case == 'upper':
        value = value.upper()
    elif case == 'lower':
        value = value.lower()

    return unidecode.unidecode(
               clean_string(
                   unicoder(value)))

def split_to_dict(value, sep):
    if not isinstance(value, dict):
        return False

    r = {}

    for key, val in value.iteritems():
        ref  = r
        keys = key.split(sep)
        xlen = len(keys)

        for i, k in enumerate(keys):
            if xlen != i + 1:
                if k not in ref:
                    ref[k] = {}
                ref = ref[k]
            else:
                ref[k] = val

    return r

def merge(current, default):
    if isinstance(current, dict) and isinstance(default, dict):
        for key, value in default.iteritems():
            if key not in current:
                current[key] = value
            else:
                current[key] = merge(current[key], value)

    return current

def has_len(value, default=False, retvalue=False):
    if not is_scalar(value):
        return default

    if isinstance(value, bool):
        value = int(value)

    if not isinstance(value, basestring):
        value = str(value)

    if not value:
        return default

    return retvalue is False or value

def unicoder(value):
    if value is None or isinstance(value, unicode):
        return value

    try:
        value = value.decode('utf8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            value = value.decode('latin1')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass

    return value

def unidecoder(value):
    if value is None or not isinstance(value, unicode):
        return value

    try:
        value = value.encode('utf8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            value = value.encode('latin1')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass

    return value

def make_dirs(path):
    if not path:
        return

    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST or not os.path.isdir(path):
            raise

def send_email(xfrom, to, subject, body, cc=None, bcc=None, attachments=None, host=None):
    if not has_len(host):
        host        = 'localhost'

    outer           = MIMEMultipart()

    if has_len(xfrom):
        outer['From']   = xfrom
    elif isinstance(xfrom, (list, tuple)) and len(xfrom) == 2:
        outer['From']   = "%s <%s>" % (Header(unidecoder(xfrom[0]), 'utf-8'), xfrom[1])
        xfrom           = xfrom[1]
    else:
        raise ValueError("Invalid e-mail sender. (from: %r)" % xfrom)

    outer['Date']   = formatdate(localtime=True)
    smtp            = smtplib.SMTP(host)

    if has_len(to):
        to          = [to]

    if isinstance(to, (list, tuple)):
        to          = list(to)
        outer['To'] = COMMASPACE.join(list(to))
    else:
        raise ValueError("Invalid e-mail recipients. (to: %r)" % to)

    if has_len(cc):
        cc          = [cc]

    if isinstance(cc, (list, tuple)):
        to         += list(cc)
        outer['Cc'] = COMMASPACE.join(list(cc))

    if has_len(bcc):
        bcc         = [bcc]

    if isinstance(bcc, (list, tuple)):
        to         += list(bcc)

    if has_len(subject):
        outer['Subject']    = Header(unidecoder(subject), 'utf-8')

    if has_len(body):
        outer.attach(MIMEText(unidecoder(body), _charset='utf-8'))

    if has_len(attachments):
        attachments = [attachments]

    if attachments:
        if isinstance(attachments, (list, tuple)):
            attachments = dict(zip(attachments, len(attachments) * ('application/octet-stream',)))

        for attachment in sorted(attachments.iterkeys()):
            fp          = open(attachment, 'rb')
            part        = MIMEBase('application', 'octet-stream')
            part.set_type(attachments[attachment])
            filename    = os.path.basename(attachment)
            part.set_payload(fp.read())
            fp.close()
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=filename)
            outer.attach(part)

    smtp.sendmail(xfrom, to, outer.as_string())
    smtp.quit()

def rm_rf(path):
    """
    Recursively (if needed) delete path.
    """
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)

def flush_sync_file_object(fo):
    """
    Flush internal buffers of @fo, then ask the OS to flush its own buffers.
    """
    fo.flush()
    os.fsync(fo.fileno())

def file_writelines_flush_sync(path, lines):
    """
    Fill file at @path with @lines then flush all buffers
    (Python and system buffers)
    """
    fp = open(path, 'w')
    try:
        fp.writelines(lines)
        flush_sync_file_object(fp)
    finally:
        fp.close()

def file_w_create_directories(filepath):
    """
    Recursively create some directories if needed so that the directory where
    @filepath must be written exists, then open it in "w" mode and return the
    file object.
    """
    dirname = os.path.dirname(filepath)

    if dirname and dirname != os.path.curdir and not os.path.isdir(dirname):
        os.makedirs(dirname)

    return open(filepath, 'w')

def file_w_tmp(lines, path = None, mode = 'w+'):
    with tempfile.NamedTemporaryFile(mode, delete = False) as f:
        LOG.debug("writing temporary file: %r", f.name)
        f.writelines(lines)
        flush_sync_file_object(f)

    if not path:
        return f.name

    if os.path.isfile(path):
        LOG.debug("overwriting file: %r", path)
        stat = os.stat(path)
        os.chmod(f.name, stat.st_mode)
        os.chown(f.name, stat.st_uid, stat.st_gid)
    LOG.debug("move file: %r to %r", f.name, path)
    shutil.move(f.name, path)

    return path

def touch(fname, times = None, exists = False):
    if exists:
        if os.path.exists(fname):
            touch(fname, times, False)
        return

    with open(fname, 'a'):
        os.utime(fname, times)
    return

def ps_info(pid):
    proc        = psutil.Process(pid)
    r           = proc.as_dict(attrs    = ['pid',
                                           'name',
                                           'status',
                                           'create_time',
                                           'num_threads'])
    r['cpu_percent'] = 0.0
    r['mem_percent'] = 0.0
    r['mem_info']    = proc.memory_info()
    r['uptime']      = time.time() - proc.create_time()

    pgid        = os.getpgid(pid)
    for gproc in psutil.process_iter():
        try:
            if os.getpgid(gproc.pid) == pgid and gproc.pid != 0:
                r['cpu_percent'] += proc.cpu_percent(interval=0.1)
                r['mem_percent'] += proc.memory_percent()
        except (psutil.Error, OSError):
            continue

    return r

def ps_kill(filename):
    rfilename   = os.path.realpath(filename)

    for process in psutil.process_iter():
        try:
            for x in process.memory_maps():
                if x.path == rfilename:
                    return process.kill()
        except psutil.AccessDenied:
            continue

    return

# States for linesubst()
NORM    = object()
ONE     = object()
TWO     = object()
LIT     = object()
TLIT    = object()
TERM    = object()

def linesubst(line, variables):
    """
    In a string, substitute '{{varname}}' occurrences with the value of
    variables['varname'], '\\' being an escaping char...
    If at first you don't understand this function, draw its finite state
    machine and everything will become crystal clear :)
    """
    # trivial no substitution early detection:
    if '{{' not in line and '\\' not in line:
        return line
    st = NORM
    out = ""
    curvar = ""
    for c in line:
        if st is NORM:
            if c == '{':
                st = ONE
            elif c == '\\':
                st = LIT
            else:
                out += c
        elif st is LIT:
            out += c
            st = NORM
        elif st is ONE:
            if c == '{':
                st = TWO
            elif c == '\\':
                out += '{'
                st = LIT
            else:
                out += '{' + c
                st = NORM
        elif st is TWO:
            if c == '\\':
                st = TLIT
            elif c == '}':
                st = TERM
            else:
                curvar += c
        elif st is TLIT:
            curvar += c
            st = TWO
        elif st is TERM:
            if c == '}':
                if curvar not in variables:
                    LOG.warning("Unknown variable %r detected, will just be replaced by an empty string", curvar)
                else:
                    LOG.debug("Substitution of {{%s}} by %r", curvar, variables[curvar])

                    value = variables[curvar]
                    if isinstance(value, (float, int, long)):
                        value = str(value)

                    out += value
                curvar = ''
                st = NORM
            elif c == '\\':
                curvar += '}'
                st = TLIT
            else:
                curvar += '}' + c
                st = TWO
    if st is not NORM:
        LOG.warning("st is not NORM at end of line: " + line)
        LOG.warning("returned substitution: " + out)
    return out

def txtsubst(lines, variables, target_file=None, charset=None):
    """
    Log that target_file is going to be generated, and calculate its
    content by applying the linesubst() transformation with the given
    variables to each given lines.
    """
    if target_file:
        LOG.info("In process of generating file %r", target_file)

    if not charset:
        return [linesubst(line, variables) for line in lines]

    ret = []
    for line in lines:
        linesub = linesubst(line, variables)
        if isinstance(line, unicode):
            ret.append(linesub.encode(charset))
        else:
            ret.append(linesub)
    return ret

def rand_str(size=8):
    return ''.join(random.SystemRandom().choice(list(_alphanum)) for _ in range(size))

def re_unescape(pattern):
    s           = []
    alphanum    = _alphanum
    backslash   = False

    for c in pattern:
        if c in alphanum:
            s.append(c)
        elif c == "\\":
            if backslash:
                s.append(c)
            else:
                backslash = True
                continue
        else:
            s.append(c)
        backslash = False
    return ''.join(s)

def load_patterns_from_file(filename):
    r   = set()
    f   = None

    try:
        with open(filename, 'r') as f:
            for line in f.readlines():
                pattern = line.strip()
                if pattern and not pattern.startswith('#'):
                    r.add(pattern)
    finally:
        if f:
            f.close()

    return r

def gzipfile(src, dst, level = 9, delete = False):
    f_src = None
    f_dst = None

    try:
        with open(src, 'rb') as f_src:
            f_dst = gzip.open(dst, 'wb', level)
            while True:
                buf = f_src.read(BUFFER_SIZE)
                if not buf:
                    break
                f_dst.write(buf)
        f_src.close()
        if delete:
            os.unlink(src)
    finally:
        if f_src and not f_src.closed:
            f_src.close()
        if f_dst:
            f_dst.close()

def load_yaml(stream, Loader = YamlLoader):
    return yaml.load(stream, Loader = Loader)

def dump_yaml(data, stream = None, Dumper = YamlDumper, **kwds):
    return yaml.dump(data, stream, Dumper, **kwds)

def load_yaml_file(uri):
    (c, b, r) = (None, None, None)

    try:
        b = StringIO()
        c = pycurl.Curl()
        c.setopt(c.URL, uri)
        c.setopt(c.WRITEFUNCTION, b.write)
        c.perform()
        c.close()
        r = load_yaml(b.getvalue())
    except pycurl.error, e:
        LOG.error(repr(e))
    finally:
        if b:
            b.close()
        if c:
            c.close()

    return r

def section_from_yaml_file(uri, key = '__section', config_dir = None):
    section = None

    u = list(urisup.uri_help_split(uri))
    if not u[0] and u[2]:
        u[0] = 'file'
        if config_dir and not u[2].startswith('/'):
            u[2] = "%s/%s" % (config_dir, u[2])

    if u[3]:
        q = []
        for k, v in u[3]:
            if k == key:
                section = v
            else:
                q.append((k, v))
        u[3] = q

    r = load_yaml_file(urisup.uri_help_unsplit(u))

    if section \
       and isinstance(r, dict) \
       and section in r:
        return r[section]

    return r
