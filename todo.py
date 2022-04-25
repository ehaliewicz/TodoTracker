from dataclasses import dataclass
import datetime
import os
import stat
import re
import sys
import timeit
import traceback
import time

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

    def finish(self):
        self.finished = True

    def clone(self):
        return TodoItem(name=self.name, duration=self.duration, finished=self.finished, tag=self.tag)
    
    def finish_with_custom_duration(self, duration):
        self.duration = duration
        self.finished = True

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
    assert time_str[-1] == 'm'
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
            res += "({}) ".format(idx)
        res += "# {}\n".format(todo)

    return res


def read_cur_todo_log():
    # if log for today exists, read that instead of the original todo list
    f = get_log_filename()
    if not os.path.exists(f):
        f = sys.argv[1]
    return read_todo_file(f)

def read_todo_file(file):
    def inner():
        with open(file) as f:
            return read_todo_lines((line for line in f))

    return cache_fetch_or_calculate(file, inner)


def calc_percentage(todos):
    total_items = len(todos)
    completed_items = sum(todo.is_done() for todo in todos)
    total_time = sum(todo.duration for todo in todos)
    completed_time = sum(todo.time() for todo in todos)

    tasks_pct = completed_items*100/total_items
    time_pct = completed_time*100/total_time
    return tasks_pct, time_pct

def calc_time(todos):
    return sum(todo.time() for todo in todos)


def read_all_log_files():
    return (read_todo_file(f) for f in os.listdir(".") if f.endswith("_log.txt"))

def calc_all_past_times():
    all_todo_logs = list(read_all_log_files())
    days = len(all_todo_logs)
    return sum(calc_time(todo_log) for todo_log in all_todo_logs), days


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
    print("All tags:")
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
    



def repl():
    print_todos(read_cur_todo_log())
    
    while True:

        line = input("> ")
        cmd = line.rstrip().split()

        
        
        try:
            
            if len(cmd) == 0:
                raise Exception("Empty command.")
            op = cmd[0]
            params = cmd[1:]
            # commands are
            if op == 'l':  # list items
                print_todos(read_cur_todo_log())

            elif op == 'uc': # unmark an item as complete
                if len(params) != 1:
                    raise Exception("No task specified")
                idx = int(params[0])
                todos = read_cur_todo_log()
                todos[idx].uncomplete()
                
                
                save_todo_log(todos)
                print_todos(todos)                

            elif op == 'c':  # mark an item as complete
                if len(params) != 1:
                    raise Exception("No task specified")

                idx = int(params[0])
                todos = read_cur_todo_log()
                todos[idx].finish()
                
                save_todo_log(todos)
                print_todos(todos)
                
            elif op == 'cd':  # duplicate an item and mark it as complete 
                if len(params) != 1:
                    raise Exception("No task specified")
                
                idx = int(params[0])
                todos = read_cur_todo_log()

                ntodo = todos[idx].clone()
                todos.insert(idx+1, ntodo)
                todos[idx+1].finish()
                
                save_todo_log(todos)
                print_todos(todos)

            elif op == 'ct':
                if len(params) != 2:
                    raise Exception("No task and/or time specified")

                idx = int(params[0])
                time_str = params[1]
                time_duration = parse_time(time_str)

                todos = read_cur_todo_log()

                todos[idx].finish_with_custom_duration(time_duration)
                save_todo_log(todos)
                print_todos(todos)
                
            elif op == 'time':  # time for today
                t = calc_time(read_cur_todo_log())
                print("Today's time: {}m / {:.2f}hr".format(t, t/60))
                
            elif op == 'ctime':  # cumulative time
                time,days = calc_all_past_times()
                hours = time/60
                hours_per_day = time/days/60
                print("Cumulative time: {}m / {:.2f}hr over {} days".format(time, time/60, days))
                print("{:.2f} hours per day avg.".format(hours_per_day))
            elif op == 'tags':
                print_tags(read_cur_todo_log())

            elif op == 'ctags':
                print_all_tags()
                
            elif op == 'q': # quit
                break 
            elif op == 'cache':  # print cache stats
                print("cache hits/misses: {}/{}".format(cache_stats['hits'], cache_stats['misses']))

            elif op == 'h' or op == 'help':
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
                print("     l                - list todo items")
                print("     c {num}          - complete a todo item")
                print("    cd {num}          - complete a duplicate of a todo item")
                print("     c {num} {time}m  - complete a todo item with a specified time in minutes")
                print("    uc {num}          - un-complete a todo item") 
                print("  time                - show time spent today")
                print(" ctime                - show cumulative time for all days")
                print("  tags                - show completed task tags for today")
                print(" ctags                - show completed task tags for all days")
                print(" cache                - show cache info")
                print("     q                - quit")
                print("h/help                - show this help screen")

            else:
                raise Exception("Unknown command '{}'".format(op))
            
        except Exception as e:
            print(str(e))
            

def main(f):
    todos = read_cur_todo_log()
    save_todo_log(todos)
    repl()


if __name__ == '__main__':
    main(sys.argv[1])
