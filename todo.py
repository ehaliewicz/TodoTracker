import argparse
from dataclasses import dataclass
import datetime
import itertools
import json
import os
import stat
import re
import sys
import timeit
import traceback
import time

VERSION = "0.3"


# new   - create new item
# desc  - update description
# comp  - toggle completion
# time  - set time
# tag   - set tag
# clone - add new entry based on item


# todo item definition 
@dataclass
class TodoItem:
    name: str
    duration: int
    finished: bool
    tag: str
    

    def time(self):
        return self.duration if self.finished else 0

    def is_done(self):
        return self.finished

    def toggle_complete(self):
        self.finished = not self.finished

    def clone(self):
        return TodoItem(
            name=self.name, duration=self.duration,
            finished=self.finished, tag=self.tag)
    
    def set_duration(self, duration):
        self.duration = duration

    def uncomplete(self):
        self.finished = False

    def __str__(self):
        tag_str = ""
        if self.tag != "":
            tag_str = "%{}".format(self.tag)
            
        if self.finished:
            return "DONE {} ({}m) {}".format(self.name, self.duration, tag_str)
        else:
            return "{} ({}m) {}".format(self.name, self.duration, tag_str)

    def to_db_tuple(self, day):
        return (self.name, 1 if self.finished else 0, self.duration, self.tag, day)



# file caching
parsed_file_cache = {}

def clear_file_in_cache(f):
    if f in parsed_file_cache:
        del parsed_file_cache[f]

cache_stats = {'hits': 0, 'misses': 0}

def cache_fetch_or_calculate(f, func):
    if f not in parsed_file_cache:
        update_time = time.time()
        parsed_file = func()
        parsed_file_cache[f] = (update_time, parsed_file)
        cache_stats['misses'] += 1
        return parsed_file

    file_update_time = os.stat(f)[stat.ST_MTIME]
    last_parse_time, last_parsed = parsed_file_cache[f]
    
    if file_update_time > last_parse_time:
        update_time = time.time()
        parsed_file = func()
        parsed_file_cache[f] = (update_time, parsed_file)
        cache_stats['misses'] += 1
        return parsed_file

        
    _,parsed_file = parsed_file_cache[f]
    cache_stats['hits'] += 1
    return parsed_file



def reset_file_cache():
    global parsed_file_cache
    parsed_file_cache = {}
            

def skip_char(c, line):
    if len(line) == 0:
        raise Exception("Expected '{}' but got EOL".format(c))
    if line[0] != c:
        raise Exception("Expected '{}' but got '{}'".format(c, line[0]))

    return line[1:]

def skip_string(s, line):
    while len(s) > 0:
        line = skip_char(s[0], line)
        s = s[1:]
    return line
        
def skip_whitespace(line):
    idx = 0
    rem = len(line)
    while rem > 0 and line[idx].isspace():
        #line = line[1:]
        idx += 1
        rem -= 1
        
    return line[idx:]

def parse_time(time_str):
    assert time_str[-1] == 'm', "Expected time with 'm' suffix"
    return int(time_str[:-1])
    
### parsing and unparsing
def parse_todo_line(line):
    line = skip_char('#', line)
    line = skip_whitespace(line)

    done = False
    try: 
        line = skip_string('DONE', line)
        done = True
    except:
        pass

    line = skip_whitespace(line)

    spl = line.split(" (", 1)
    todo_name, line = spl[0],spl[1]
    
    todo_name = todo_name.rstrip()
    
    spl = line.split(")", 1)
    time,line = spl[0],spl[1]

    time_duration = parse_time(time)
        
    line = skip_whitespace(line)

    tag = ""
    if len(line) > 0:
        # parse a tag
        line = skip_char('%', line)
        tag = line.strip()
    
    return TodoItem(name=todo_name, duration=time_duration, finished=done, tag=tag)


def read_todo_lines(lines):
    """ Parses a list of lines from a todo file into a list of TodoItem(s)

    SYNTAX = 
        ### - start or end block comment

        # - start a todo item, followed by the name and the time formatted like '(15m)'

        # DONE - start a finished todo item, followed by the name and the time formatted like '(15m)'
    """

    todos = []
    in_comment = False

    # hacky parsing here :^)
    for line in lines:
        spl = line.strip().split()
        
        # skip empty lines
        if len(spl) == 0:
            continue

        # start or end comment
        elif spl[0] == '###':
            in_comment = not in_comment
            continue

        # continue comment
        elif in_comment:
            continue

        # parse a todo item
        elif spl[0] == '#':
            todo_item = parse_todo_line(line)
            
            todos.append(todo_item)

        else:
            # got other kind of comment (anything not starting with '#' or '###' is a comment)
            pass

    return todos

def get_log_filename():
    date = datetime.date.today()
    return "{}_log.txt".format(date)

def get_last_seven_days_filenames():
    for i in [6,5,4,3,2,1,0]:
        d = datetime.date.today() - datetime.timedelta(days=i)
        yield '{}_log.txt'.format(d)

def save_todo_log(todos):
    f = get_log_filename()

    clear_file_in_cache(f)

    with open(f, 'w') as of:
        of.write(serialize_todos(todos))

        
def serialize_todos(todos, repl=False):
    """Serializes todos into text format"""
    res = ""
    for idx, todo in enumerate(todos):
        if repl:
            res += "({}) ".format(idx).rjust(5)
        res += "# {}\n".format(todo)

    return res

def read_todo_file_if_exists(f, backup_f=None):
    if os.path.exists(f):
        return read_todo_file(f)
    if backup_f:
        return read_todo_file(backup_f)

def read_cur_todo_log(todo_list_file):
    # if log for today exists, read that instead of the original todo list
    f = get_log_filename()
    return read_todo_file_if_exists(f, todo_list_file)
    

def read_todo_file(file):
    def inner():
        with open(file) as f:
            return read_todo_lines((line for line in f))

    return cache_fetch_or_calculate(file, inner)

command_metadata = {
    'list':            ([], 'list tasks'),
    'toggle-complete': (['idx'], 'toggle completion of task'),
    'set-time':        (['idx', 'time'], 'set duration of task'),
    'duplicate':       (['idx'], 'duplicate a task'),
    'new':             (['new-task'], 'create a new task'),
    'delete':          (['idx'], 'delete a task'),
    'time':            ([], 'show time spent today'),
    'week-time':       ([], 'print time for the last week'),
    'cumulative-time': ([], 'show cumulative time for all days'),
    'tags':            ([], 'show completed task tags for today'),
    'cumulative-tags': ([], 'show completed task tags for all days'),
    'quit':            ([], 'quit'),
    'help':            ([], 'show this help information'),
}

def generate_help_str(raw_config):
    #max_left_side = 0
    #keyword_sz = 0
    max_command_name = 0
    max_params = 0
    for cmd,keyword_list in raw_config.items():
        params,desc = command_metadata[cmd]
        keyword_sz = len('/'.join(keyword_list))
        params_sz = len(' '.join('{'+param+'}' for param in params))
        #max_left_side = max(max_left_side, sz)
        max_command_name = max(max_command_name, keyword_sz)
        max_params = max(max_params, params_sz)
    s = ""
    
    for cmd,keyword_list in raw_config.items():
        params,desc = command_metadata[cmd]
        command_name = '/'.join(keyword_list).rjust(max_command_name)
        params = ' '.join('{'+param+'}' for param in params).ljust(max_params)
        
        left_side = '{} {}'.format(
            command_name,
            params,
        )
        s += '{} - {}\n'.format(
            left_side,#.ljust(max_left_side),
            desc)

    return s
        
        
def read_config_file(cfg_file):
    if not os.path.exists(cfg_file):
        return DEFAULT_CONFIG

    with open(cfg_file) as f:
        raw_config = json.load(f)

    help_str = generate_help_str(raw_config)

    cfg = {}
    for cmd,keyword_list in raw_config.items():
        for keyword in keyword_list:
            if keyword in cfg:
                raise Exception("Duplicate key command '{}' in config".format(keyword))
            cfg[keyword] = cmd
    return cfg, help_str
    

def calc_percentage(todos):
    total_items = len(todos)
    completed_items = sum(todo.is_done() for todo in todos)
    total_time = sum(todo.duration for todo in todos)
    completed_time = sum(todo.time() for todo in todos)

    tasks_pct = completed_items*100/total_items
    time_pct = completed_time*100/total_time
    return tasks_pct, time_pct

def calc_time(todos):
    completed = sum(todo.time() for todo in todos)
    total = sum(todo.duration for todo in todos)
    return completed, total
    

def read_all_log_files():
    return (read_todo_file(f) for f in os.listdir(".") if f.endswith("_log.txt"))

def read_last_weeks_logs():
    for f in get_last_seven_days_filenames():
        read = read_todo_file_if_exists(f)
        if read:
            yield read
    
def calc_time_in_range(todo_logs):
    days = len(todo_logs)

    times_a, times_b = itertools.tee(calc_time(todo_log) for todo_log in todo_logs)
    completed, totals = (x[0] for x in times_a), (y[1] for y in times_b)

    return sum(completed), sum(totals), days

def calc_all_past_times():
    all_todo_logs = list(read_all_log_files())
    return calc_time_in_range(all_todo_logs)


def calc_last_week_time():
    last_weeks_logs = list(read_last_weeks_logs())
    res = calc_time_in_range(last_weeks_logs)
    print(res)
    return res
    
def print_todos(todos):
    print(serialize_todos(todos, True))
    task_pct,time_pct = calc_percentage(todos)
    print("{:.2f}% tasks done".format(task_pct))
    print("{:.2f}% time done".format(time_pct))
    
def print_tags_inner(cnt_tbl, time_tbl):
    
    s = ""
    for tag,cnt in cnt_tbl.items():
        time = time_tbl[tag]
        time_str = "{}m / {:.2f}hr".format(time, time/60)
        cnt_str = "{} {}(s)".format(cnt, tag).rjust(25)
        s += "{}: {}\n".format(cnt_str, time_str)
    print(s)
    
def print_tags(todos):
    cnt_tbl,time_tbl = gather_tags(todos)
    print("Todays tags:")
    print_tags_inner(cnt_tbl, time_tbl)

def print_all_tags():
    cnt_tbl,time_tbl = gather_all_tags()
    print("Cumulative tags:")
    print_tags_inner(cnt_tbl, time_tbl)


def gather_tags(todos):
    cnt_tbl = {}
    time_tbl = {}
    for todo in todos:
        if not todo.is_done():
            continue
        if todo.tag == "":
            tag = "[untagged]"
        else:
            tag = todo.tag
        if tag not in cnt_tbl:
            cnt_tbl[tag] = 0
            time_tbl[tag] = 0
        cnt_tbl[tag] += 1
        time_tbl[tag] += todo.duration
    return cnt_tbl, time_tbl


def gather_all_tags():
    all_todo_logs = read_all_log_files()
    
    tbl = {}

    flat_todos = []
    for todos in all_todo_logs:
        flat_todos += todos

    return gather_tags(flat_todos)
    



def repl(todo_list_file, config, help_str):

    print("""
  .-----------------------------.
  | Welcome to TodoTracker v{} |
  .-----------------------------.
"""
    .format(VERSION))
    print_todos(read_cur_todo_log(todo_list_file))
    
    while True:

        line = input("> ")
        cmd = line.rstrip().split()

        
        try:
            
            if len(cmd) == 0:
                raise Exception("Empty command.")
            op = cmd[0]
            params = cmd[1:]

            def todo_op(num_params, func):
                def inner(params):
                    if num_params != 0:
                        if len(params) != num_params:
                            raise Exception("Invalid number of parameters supplied.")
                        params = (int(p) for p in params)
                    else:
                        params = []
                    
                    todos = read_cur_todo_log(todo_list_file)
                                
                    func(todos, *params)
                    save_todo_log(todos)
                    print_todos(todos)

                return inner
        
            def duplicate(todos, idx):
                ntodo = todos[idx].clone()
                todos.insert(idx+1, ntodo)

            def new_todo_item(todos):
                l = line.split("{} ".format(op), 1)[1]
                todo_item = parse_todo_line(l)
                todos.append(todo_item)

            def delete_todo_item(todos, idx):
                del todos[idx]

            def get_hr_min(m):
                return int(m//60),int(m%60)
                
            def print_time():
                completed,total = calc_time(read_cur_todo_log(todo_list_file))
                hr,m = get_hr_min(completed)
                thr,tm = get_hr_min(total)
                print("Today's time: {}m / {}h{}m out of {}h{}m".format(completed, hr,m, thr,tm))
                
            def print_week_time():
                comp_mins, total_mins, num_days = calc_last_week_time()
                #completed,total,days = calc_all_past_times()
                comp_hr,comp_rem_mins = get_hr_min(comp_mins)

                mins_per_day = comp_mins/num_days
                mins_per_7_days = comp_mins/7
                
                hrd,md = get_hr_min(mins_per_day)
                whrd,wmd = get_hr_min(mins_per_7_days)

                print("Cumulative time: {}m / {}h{}m over {} days studied".format(
                    comp_mins, comp_hr, comp_rem_mins, num_days
                ))
                print("{}h{}m per days studied avg.".format(hrd, md))
                print("{}h{}m per day of week avg.".format(whrd, wmd))
                
            def print_cumulative_time():
                comp_mins, total_mins, num_days = calc_all_past_times()
                #completed,total,days = calc_all_past_times()
                comp_hr,comp_rem_mins = get_hr_min(comp_mins)

                mins_per_day = comp_mins/num_days
                
                hrd,md = get_hr_min(mins_per_day)

                print("Cumulative time: {}m / {}h{}m over {} days".format(
                    comp_mins, comp_hr, comp_rem_mins, num_days
                ))
                print("{}h{}m per day avg.".format(hrd, md))
                

            def print_help(params):
                print(
"""
                TODO TRACKER
                
Parses a list of lines from a todo file, lets you mark them as complete, 
and automatically creates logs to track historical progress.
            
Usage
                todo.py todo_list_file
Syntax
    ### - start or end block comment
                
    # - Denotes a todo item, followed by the name and the time formatted like '(15m)'  
        Can be optionally tagged like %tag-1 (the tag must be the last part of the line)
        e.g.
              # listen to podcast (15m)
              # watch an episode of a tv show (20m) %tv-show
                
                
    # DONE - Used by the program to mark a completed todo item in a log.  Save syntax as above.
                
    - Anything else is considered a comment.
                
""")
                print(help_str)

            cmd_table = {
                'list': lambda params: print_todos(read_cur_todo_log(todo_list_file)),
                'toggle-complete': todo_op(1, lambda todos, idx: todos[idx].toggle_complete()),
                'duplicate': todo_op(1, duplicate),
                'quit': lambda p: sys.exit(),
                'set-time': todo_op(
                    2,
                    lambda todos, idx, dur: todos[idx].set_duration(dur)
                ),
                'new': todo_op(0, new_todo_item),
                'delete': todo_op(1, delete_todo_item),
                
                'time':            lambda params: print_time(),
                'week-time':       lambda params: print_week_time(),
                'cumulative-time': lambda params: print_cumulative_time(),
                'tags':            lambda params: print_tags(read_cur_todo_log(todo_list_file)),
                'cumulative-tags': lambda params: print_all_tags(),
                'help':            print_help,
                
            
            }

            if op not in config:
                raise Exception("Unknown keyword '{}'".format(op))
            
            cmd_str = config[op]

            if cmd_str not in cmd_table:
                raise Exception("Unknown command '{}'".format(cmd_str))
                
            cmd_table[cmd_str](params)
            
        except Exception as e:
            print(traceback.format_exc())
            print(str(e))
            

def main(todo_list_file, config_file):
    todos = read_cur_todo_log(todo_list_file)
    cfg,help_str = read_config_file(config_file)
    save_todo_log(todos)
    
    repl(todo_list_file=todo_list_file, config=cfg, help_str=help_str)


parser = argparse.ArgumentParser(description='Track todo items and time.')
parser.add_argument('--todo', metavar='todo_list_file', type=str, default='todo_list.txt')
parser.add_argument('--config', metavar='config_file', type=str, default='config.json')

if __name__ == '__main__':
    args = parser.parse_args()
    main(todo_list_file=args.todo, config_file=args.config)
