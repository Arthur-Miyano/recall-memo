# Python 全栈八股文

> 涵盖 Python 基础、Vue 前端、FastAPI 框架、后端/Web 基础、并发编程、Linux & 部署、项目实战

---

## 目录

- [第 1 章 Python 基础](#第-1-章-python-基础)
- [第 2 章 Vue 前端](#第-2-章-vue-前端)
- [第 3 章 FastAPI 框架](#第-3-章-fastapi-框架)
- [第 4 章 后端/Web 基础](#第-4-章-后端web-基础)
- [第 5 章 并发编程](#第-5-章-并发编程)
- [第 6 章 Linux & 部署 & 中间件](#第-6-章-linux--部署--中间件)
- [第 7 章 项目](#第-7-章-项目)

---




---


# 第 1 章：Python 基础

> 本章深入讲解 Python 核心机制与底层原理，涵盖内存管理、装饰器、生成器、元类、MRO、闭包等面试高频考点。

---

## 1. Python 内存管理与垃圾回收

### 概念解释

Python 的内存管理机制是面试中的核心考点，它主要由三个层次协同工作：内存分配器（pymalloc）、引用计数（Reference Counting）和循环垃圾回收器（Cycle GC）。理解这三者的配合，才能真正理解 Python 中对象的生命周期。

**引用计数**是 Python 最基础的垃圾回收机制。每个 Python 对象在 C 层都有一个 `ob_refcnt` 字段，记录着有多少个指针指向该对象。当引用计数变为 0 时，对象会被立即销毁，内存被释放。这种机制简单高效，但存在致命缺陷：无法处理循环引用。当对象 A 引用对象 B，同时对象 B 又引用对象 A 时，即使外部没有任何引用指向它们，两者的引用计数都不会降到 0，导致内存泄漏。

为解决循环引用问题，Python 引入了**分代垃圾回收器（Generational GC）**。该回收器维护三个代（generation 0、1、2），新创建的对象放入第 0 代。每当第 0 代对象数量超过阈值时，触发一次垃圾回收扫描，检测并打破循环引用。存活下来的对象会被提升到下一代。代越老，触发回收的频率越低——因为经验表明，存活越久的对象越不容易成为垃圾。这种"分代假设"大幅提升了 GC 效率。

**GIL（Global Interpreter Lock，全局解释器锁）**是 CPython 实现中的一个互斥锁，它确保同一时刻只有一个线程在执行 Python 字节码。GIL 存在的根本原因是 CPython 的内存管理不是线程安全的：引用计数的增减操作如果没有锁保护，在多线程环境下会产生竞争条件。GIL 使得多线程程序在 CPU 密集型任务上无法真正并行，但在 I/O 密集型任务中，线程会在等待 I/O 时释放 GIL，因此仍有一定并发能力。

### 代码示例

```python
import sys
import gc

# 引用计数基础演示
a = [1, 2, 3]
print(f"引用计数: {sys.getrefcount(a) - 1}")  # 减1因为getrefcount本身会临时增加计数

b = a  # b也指向同一个列表
print(f"赋值后引用计数: {sys.getrefcount(a) - 1}")

del b  # 删除引用
print(f"删除b后引用计数: {sys.getrefcount(a) - 1}")

# 循环引用演示
class Node:
    def __init__(self, name):
        self.name = name
        self.next = None
        print(f"创建: {self.name}")
    
    def __del__(self):
        print(f"销毁: {self.name}")

# 创建循环引用
node_a = Node("A")
node_b = Node("B")
node_a.next = node_b
node_b.next = node_a

# 删除外部引用后，由于循环引用，__del__不会被立即调用
del node_a
del node_b

# 手动触发垃圾回收
gc.collect()  # 输出 "销毁: B" 和 "销毁: A"

# 查看分代回收阈值
print(f"GC阈值: {gc.get_threshold()}")  # 默认(700, 10, 10)

# 禁用/启用GC
# gc.disable()
# gc.enable()
```

### 常见面试题

**Q1：GIL 是什么？它如何影响多线程程序？**

A：GIL（全局解释器锁）是 CPython 中的一个互斥锁，它保证同一时刻只有一个线程在执行 Python 字节码。对于 CPU 密集型任务，多线程无法利用多核 CPU 实现真正的并行，因为线程在争夺 GIL；此时应使用多进程（`multiprocessing`）来绕过 GIL。对于 I/O 密集型任务（网络请求、文件读写），线程在等待 I/O 时会释放 GIL，其他线程得以执行，因此多线程仍有并发效果。如果必须使用多线程处理 CPU 密集型任务，可以考虑使用 `Cython` 释放 GIL，或者换用 `Jython`、`IronPython` 等没有 GIL 的实现。

**Q2：如何检测和调试循环引用导致的内存泄漏？**

A：可以使用 `gc` 模块的 `gc.garbage`（在开启 `gc.DEBUG_SAVEALL` 时）或 `objgraph` 库来可视化引用关系。`gc.set_debug(gc.DEBUG_LEAK)` 可以帮助追踪不可达对象。另外，`weakref` 模块可以创建不增加引用计数的弱引用，是打破循环引用的常用手段。在 `__del__` 方法中应避免复杂的逻辑，因为循环引用中的对象可能无法被正常析构。

---

## 2. 深浅拷贝 vs 赋值

### 概念解释

在 Python 中，变量赋值操作 `a = b` 并不会创建新的对象，而是让变量 `a` 和 `b` 指向同一个内存地址。这意味着通过 `a` 修改可变对象时，`b` 也会"看到"变化。这在面试中是一个常见陷阱题，考察候选人对 Python 对象模型的理解。

**浅拷贝（Shallow Copy）**创建一个新对象，然后将原对象中的元素引用（地址）复制到新对象中。对于不可变元素（数字、字符串、元组），浅拷贝是安全的；但对于可变元素（列表、字典等），修改新对象中的可变元素会影响原对象，因为它们内部指向的是同一个子对象。浅拷贝可以通过 `copy.copy()`、`[:]` 切片、`list()` 构造函数、`dict.copy()` 等方式实现。

**深拷贝（Deep Copy）**则会递归地创建新对象，对于原对象中的每一个元素，如果是可变对象，都会创建其完整副本。深拷贝通过 `copy.deepcopy()` 实现，它会递归遍历对象图，复制所有层次的数据，确保新旧对象完全独立。深拷贝的实现非常精巧：它维护了 `memo` 字典来记录已经拷贝过的对象，从而处理循环引用的情况，避免无限递归。

理解三者的区别，关键在于认识到 Python 中变量存储的是对象的引用，而非对象本身。`is` 运算符比较的是身份（内存地址），`==` 运算符比较的是值。

### 代码示例

```python
import copy

# ================ 赋值 ================
a = [1, 2, [3, 4]]
b = a  # 赋值：a 和 b 指向同一个对象
print(f"赋值后 a is b: {a is b}")  # True

b[0] = 999
print(f"修改b后a: {a}")  # [999, 2, [3, 4]] — a也被改了！

# ================ 浅拷贝 ================
c = [1, 2, [3, 4]]
d = copy.copy(c)  # 浅拷贝：创建新列表，但内部元素共享引用

print(f"浅拷贝 c is d: {c is d}")      # False
print(f"c[2] is d[2]: {c[2] is d[2]}")  # True — 内部列表共享！

d[0] = 999         # 修改不可变元素，不影响c
d[2].append(5)     # 修改可变子对象，会影响c！
print(f"浅拷贝后 c: {c}")  # [1, 2, [3, 4, 5]] — 子对象被改了

# 浅拷贝的其他方式
e = c[:]           # 切片浅拷贝
f = list(c)        # 构造函数浅拷贝
g = copy.copy(c)   # copy模块浅拷贝

# ================ 深拷贝 ================
h = [1, 2, [3, 4]]
i = copy.deepcopy(h)  # 深拷贝：递归复制所有层次

print(f"深拷贝 h is i: {h is i}")      # False
print(f"h[2] is i[2]: {h[2] is i[2]}")  # False — 完全独立

i[2].append(5)
print(f"深拷贝后 h: {h}")  # [1, 2, [3, 4]] — 完全不受影响

# ================ 自定义深拷贝行为 ================
class Person:
    def __init__(self, name, friends=None):
        self.name = name
        self.friends = friends or []
    
    def __deepcopy__(self, memo):
        # 自定义深拷贝逻辑
        print(f"自定义深拷贝: {self.name}")
        new_person = Person(self.name)
        new_person.friends = copy.deepcopy(self.friends, memo)
        return new_person
    
    def __repr__(self):
        return f"Person({self.name})"

p1 = Person("Alice", ["Bob", "Charlie"])
p2 = copy.deepcopy(p1)
p2.friends.append("David")
print(f"p1的朋友: {p1.friends}")  # ['Bob', 'Charlie']
print(f"p2的朋友: {p2.friends}")  # ['Bob', 'Charlie', 'David']
```

### 常见面试题

**Q1：以下代码的输出是什么？**

```python
def extend_list(val, lst=[]):
    lst.append(val)
    return lst

print(extend_list(1))
print(extend_list(2))
```

A：输出是 `[1]` 和 `[1, 2]`。这是一个经典的 Python 陷阱：函数默认参数在函数定义时求值，而不是每次调用时。`lst=[]` 中的空列表在模块加载时创建一次，后续调用共享同一个列表对象。修复方法是用 `None` 作为默认值：`def extend_list(val, lst=None): if lst is None: lst = []`。

**Q2：`is` 和 `==` 的区别是什么？**

A：`is` 比较的是两个对象的内存地址（身份标识），`==` 比较的是两个对象的值（调用 `__eq__` 方法）。对于小整数（-5 到 256）和短字符串，Python 会缓存对象，所以 `is` 可能返回 True，但这只是实现细节，不应依赖。判断值相等用 `==`，判断是否是同一个对象用 `is`。常见的正确使用场景：`if x is None`、`if x is True`。

---

## 3. 装饰器原理与实现

### 概念解释

装饰器（Decorator）是 Python 中一种强大的语法糖，它本质上是一个**高阶函数**——接收一个函数作为参数，并返回一个新的函数。装饰器允许我们在不修改原函数源代码的前提下，为函数添加额外的功能（如日志记录、性能计时、权限校验、缓存等）。

装饰器的语法 `@decorator` 等价于 `func = decorator(func)`。当 Python 解释器遇到带装饰器的函数定义时，会先定义函数对象，然后立即用装饰器函数包裹它，最终将返回的新函数绑定到原名称上。

**函数装饰器**是最基本的形式。实现一个装饰器时，通常会定义一个内层函数（wrapper）来替代原函数，在 wrapper 中执行前置逻辑、调用原函数、执行后置逻辑。为了保持原函数的元信息（如 `__name__`、`__doc__`），需要使用 `functools.wraps` 将原函数的元数据复制到 wrapper 上。

**带参数的装饰器**需要多一层嵌套：外层函数接收装饰器参数，返回真正的装饰器函数；中层函数接收被装饰的函数，返回 wrapper。形式为 `@decorator(arg)`，执行顺序是 `func = decorator(arg)(func)`。

**类装饰器**是用类来实现的装饰器，通过实现 `__init__`（接收被装饰函数）和 `__call__`（使实例可调用）方法。类装饰器的一个优势是可以保存状态，比闭包更加直观。

### 代码示例

```python
import functools
import time
from typing import Callable

# ================ 基础函数装饰器 ================
def my_logger(func):
    """简单的日志装饰器"""
    @functools.wraps(func)  # 保留原函数的元信息
    def wrapper(*args, **kwargs):
        print(f"[LOG] 调用 {func.__name__}，参数: {args}, {kwargs}")
        result = func(*args, **kwargs)
        print(f"[LOG] {func.__name__} 返回: {result}")
        return result
    return wrapper

@my_logger
def add(a, b):
    """两数相加"""
    return a + b

add(3, 5)
# 输出：
# [LOG] 调用 add，参数: (3, 5), {}
# [LOG] add 返回: 8

# ================ 带参数的装饰器 ================
def repeat(times):
    """重复执行指定次数的装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(times):
                print(f"第 {i+1}/{times} 次执行...")
                result = func(*args, **kwargs)
            return result
        return wrapper
    return decorator

@repeat(times=3)
def greet(name):
    print(f"Hello, {name}!")

greet("Python")

# ================ 类装饰器 ================
class CountCalls:
    """统计函数被调用次数的类装饰器"""
    def __init__(self, func: Callable):
        functools.update_wrapper(self, func)
        self.func = func
        self.count = 0
    
    def __call__(self, *args, **kwargs):
        self.count += 1
        print(f"{self.func.__name__} 被调用了 {self.count} 次")
        return self.func(*args, **kwargs)

@CountCalls
def say_hello():
    print("Hello!")

say_hello()
say_hello()

# ================ 多装饰器叠加 ================
def decorator_a(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print("A - 前")
        result = func(*args, **kwargs)
        print("A - 后")
        return result
    return wrapper

def decorator_b(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print("B - 前")
        result = func(*args, **kwargs)
        print("B - 后")
        return result
    return wrapper

@decorator_a
@decorator_b
def test():
    print("执行 test")

test()
# 执行顺序：A 前 -> B 前 -> test -> B 后 -> A 后
# 等价于 test = decorator_a(decorator_b(test))

# ================ 实际应用：缓存装饰器 ================
def lru_cache(maxsize=128):
    """简易的 LRU 缓存装饰器（示意版，非线程安全）"""
    def decorator(func):
        cache = {}
        access_order = []
        
        @functools.wraps(func)
        def wrapper(*args):
            if args in cache:
                # 移到最近使用
                access_order.remove(args)
                access_order.append(args)
                print(f"[CACHE HIT] {args}")
                return cache[args]
            
            result = func(*args)
            cache[args] = result
            access_order.append(args)
            
            # 淘汰最久未使用的
            if len(cache) > maxsize:
                oldest = access_order.pop(0)
                del cache[oldest]
                print(f"[CACHE EVICT] {oldest}")
            
            return result
        
        wrapper.cache_info = lambda: f"缓存大小: {len(cache)}"
        return wrapper
    return decorator

@lru_cache(maxsize=3)
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

print(f"fib(5) = {fib(5)}")
print(fib.cache_info())
```

### 常见面试题

**Q1：`@functools.wraps(func)` 的作用是什么？如果不使用它会有什么后果？**

A：`@functools.wraps` 是一个内置装饰器，用于将被装饰函数的 `__name__`、`__doc__`、`__module__` 等元数据复制到 wrapper 函数上。如果不使用它，被装饰后的函数名称会变成 `wrapper`，文档字符串也会丢失，这会导致调试困难（堆栈跟踪显示 `wrapper` 而不是真实函数名），并且破坏内省（introspection）功能。`wraps` 内部通过 `functools.WRAPPER_ASSIGNMENTS` 和 `WRAPPER_UPDATES` 定义了要复制的属性列表。

**Q2：如何实现一个支持可选参数的装饰器（即既可以 `@decorator` 又可以 `@decorator()` 使用）？**

A：核心思路是判断装饰器接收到的第一个参数是否是可调用对象。如果是，说明以无参数形式调用；如果不是，说明接收了配置参数。代码实现如下：

```python
def smart_decorator(func=None, *, prefix="INFO"):
    def actual_decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            print(f"[{prefix}] {f.__name__} 开始执行")
            return f(*args, **kwargs)
        return wrapper
    
    if func is not None:
        # 以 @smart_decorator 形式调用
        return actual_decorator(func)
    # 以 @smart_decorator(prefix="DEBUG") 形式调用
    return actual_decorator
```

---

## 4. 生成器与迭代器

### 概念解释

迭代器（Iterator）和生成器（Generator）是 Python 中处理序列数据的核心抽象。理解它们之间的区别和联系，是掌握 Python 高级编程的关键。

**可迭代对象（Iterable）**是指任何实现了 `__iter__()` 方法或 `__getitem__()` 方法的对象，如列表、元组、字符串、字典、集合等。`__iter__()` 方法返回一个迭代器。可以通过 `iter(obj)` 函数获取可迭代对象的迭代器。

**迭代器（Iterator）**是指实现了 `__iter__()` 和 `__next__()` 两个协议方法的对象。`__iter__()` 返回迭代器自身，`__next__()` 返回序列中的下一个元素，当没有更多元素时抛出 `StopIteration` 异常。迭代器是"一次性"的——遍历完后就耗尽，不能重置。迭代器的核心优势是**惰性求值（Lazy Evaluation）**：不需要一次性将所有数据加载到内存中。

**生成器（Generator）**是一种特殊的迭代器，它使用 `yield` 关键字来简化创建过程。生成器函数在被调用时不会立即执行，而是返回一个生成器对象。每次调用生成器对象的 `__next__()` 方法（或 `next()` 函数）时，函数执行到下一个 `yield` 语句并暂停，保存当前状态（局部变量、指令指针等），返回 `yield` 后的值。下次调用时从暂停处继续执行。这种"保存-恢复"执行状态的机制由 Python 解释器自动处理。

`yield from` 是 Python 3.3 引入的语法，用于在一个生成器中委托另一个生成器（或可迭代对象）。它会自动处理子生成器的 `Send`、`Throw` 和 `Close` 操作，是编写复杂协程和管道的重要工具。`yield from` 让生成器可以像函数调用一样组合，是 async/await 的前身概念。

### 代码示例

```python
# ================ 自定义迭代器 ================
class CountDown:
    """倒计时迭代器"""
    def __init__(self, start):
        self.start = start
    
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.start <= 0:
            raise StopIteration
        self.start -= 1
        return self.start + 1

cd = CountDown(5)
print(list(cd))  # [5, 4, 3, 2, 1]

# ================ 生成器函数 ================
def fibonacci(n):
    """生成前n个斐波那契数"""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# 惰性求值：不需要一次性计算所有数
for num in fibonacci(10):
    print(num, end=" ")
print()

# ================ 生成器表达式（内存高效） ================
# 列表推导式：一次性创建完整列表，占用大量内存
squares_list = [x**2 for x in range(1000000)]

# 生成器表达式：惰性求值，几乎不占用内存
squares_gen = (x**2 for x in range(1000000))
print(f"生成器表达式大小: {sum(1 for _ in squares_gen)} 个元素")

# ================ yield from：生成器委托 ================
def sub_generator():
    """子生成器"""
    yield "子: A"
    yield "子: B"
    return "子生成器完成"

def main_generator():
    """主生成器委托给子生成器"""
    yield "主: 开始"
    # yield from 会自动迭代子生成器的所有值
    result = yield from sub_generator()
    print(f"收到子生成器返回值: {result}")
    yield "主: 结束"

print(list(main_generator()))

# ================ 生成器的高级用法：send() ================
def accumulator():
    """累积器生成器：可以通过 send() 发送数据"""
    total = 0
    while True:
        value = yield total  # 接收外部发送的值
        if value is None:
            break
        total += value

acc = accumulator()
next(acc)  # 预激（prime）生成器
print(acc.send(10))   # 10
print(acc.send(20))   # 30
print(acc.send(5))    # 35
acc.close()

# ================ 实际应用：读取大文件 ================
def read_large_file(file_path):
    """逐行读取大文件，内存占用极小"""
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            yield line.strip()

# 模拟大文件处理
def process_lines(lines):
    """处理行的生成器管道"""
    for line in lines:
        if line and not line.startswith('#'):
            yield line.upper()

# 管道组合：多个生成器串联
sample_lines = ["hello", "# comment", "world", "", "python"]
processed = process_lines(line for line in sample_lines)
print(list(processed))  # ['HELLO', 'WORLD', 'PYTHON']
```

### 常见面试题

**Q1：`yield` 和 `return` 的区别是什么？**

A：`return` 终止函数执行并返回一个值，函数的状态（局部变量等）被销毁，再次调用从头开始。`yield` 暂停函数执行并返回一个值，函数的状态被保存，下次调用时从暂停处继续执行。生成器函数可以多次产出值，而普通函数只能返回一次。从实现层面看，`yield` 使函数变成生成器，调用时返回生成器对象而非直接执行；生成器对象在底层由 PyFrameObject 维护执行状态。

**Q2：生成器和迭代器的关系是什么？**

A：生成器是迭代器的一种实现方式。所有生成器都是迭代器（实现了 `__iter__` 和 `__next__`），但并非所有迭代器都是生成器。迭代器是一个协议/接口概念，任何实现了 `__iter__` 和 `__next__` 的对象都是迭代器。生成器是 Python 提供的便捷语法（`yield`），让创建迭代器更加简单。生成器对象（generator object）是迭代器对象（iterator object）的子类型，可以通过 `isinstance(gen, Iterator)` 验证。生成器的优势在于代码更简洁、自动处理 `StopIteration`、支持 `send()`/`throw()`/`close()` 等交互协议。

---

## 5. 元类（Metaclass）与类创建过程

### 概念解释

元类（Metaclass）是"类的类"——它控制类的创建过程。如果说类是创建对象的模板，那么元类就是创建类的模板。在 Python 中，一切皆对象，类本身也是对象，是某个元类的实例。默认情况下，所有类的元类都是 `type`。

理解元类需要先理解 `type` 的**双重身份**：
1. `type` 是一个内置函数，用于获取对象的类型（`type(obj)`）。
2. `type` 是一个元类，是所有类的默认元类。当我们用 `class` 关键字定义类时，Python 实际上在底层调用了 `type(name, bases, namespace)` 来创建类对象。

类的创建过程分为三个阶段：
1. **类定义阶段**：Python 执行 `class` 语句体，收集属性和方法，创建命名空间字典。
2. **元类调用阶段**：将类名、基类元组、命名空间字典传给元类（默认是 `type`），元类创建并返回类对象。
3. **类初始化阶段**：调用 `__init_subclass__`（如果有），完成类的初始化。

自定义元类需要继承 `type` 并覆盖 `__new__` 和/或 `__init__` 方法：
- `__new__(cls, name, bases, namespace)`：负责创建类对象（分配内存），这是最常用的扩展点。
- `__init__(cls, name, bases, namespace)`：负责初始化已创建的类对象。

元类的典型应用场景包括：
- **ORM 框架**（如 Django ORM）：自动将类属性映射为数据库字段。
- **API 注册**：自动将子类注册到某个中心注册表。
- **属性验证**：在类创建时检查属性的合法性。
- **单例模式**：控制类的实例化过程。

### 代码示例

```python
# ================ 使用 type 动态创建类 ================
def greet(self):
    return f"Hello, I'm {self.name}"

# type(name, bases, namespace) 创建类
Person = type('Person', (), {
    '__init__': lambda self, name: setattr(self, 'name', name),
    'greet': greet
})

p = Person("Alice")
print(p.greet())  # Hello, I'm Alice

# ================ 自定义元类 ================
class UpperCaseMeta(type):
    """将所有非魔术方法名转为大写的元类"""
    
    def __new__(mcs, name, bases, namespace):
        # 转换方法名：除了魔术方法，其他都转大写
        new_namespace = {}
        for key, value in namespace.items():
            if callable(value) and not key.startswith('__'):
                new_namespace[key.upper()] = value
            else:
                new_namespace[key] = value
        
        print(f"[元类] 创建类: {name}")
        return super().__new__(mcs, name, bases, new_namespace)
    
    def __init__(cls, name, bases, namespace):
        print(f"[元类] 初始化类: {name}")
        super().__init__(name, bases, namespace)

class MyClass(metaclass=UpperCaseMeta):
    def hello(self):
        return "hello"
    
    def world(self):
        return "world"

obj = MyClass()
print(obj.HELLO())  # hello
print(obj.WORLD())  # world
# print(obj.hello())  # AttributeError!

# ================ 实际应用：自动注册子类 ================
class PluginRegistry(type):
    """自动注册所有插件子类"""
    registry = {}
    
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        # 排除基类本身
        if bases and bases[0] is not object:
            mcs.registry[name] = cls
            print(f"[注册] {name} 已注册")
        return cls

class Plugin(metaclass=PluginRegistry):
    """插件基类"""
    def execute(self):
        raise NotImplementedError

class EmailPlugin(Plugin):
    def execute(self):
        return "发送邮件"

class SMSPlugin(Plugin):
    def execute(self):
        return "发送短信"

print(f"已注册插件: {list(PluginRegistry.registry.keys())}")

# ================ 单例元类 ================
class SingletonMeta(type):
    """单例元类"""
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class Database(metaclass=SingletonMeta):
    def __init__(self, connection_string):
        self.connection_string = connection_string
        print(f"初始化数据库连接: {connection_string}")

db1 = Database("postgresql://localhost")
db2 = Database("mysql://localhost")
print(f"db1 is db2: {db1 is db2}")  # True
print(f"连接字符串: {db2.connection_string}")  # postgresql://localhost

# ================ 属性验证元类 ================
class TypedMeta(type):
    """自动为带类型注解的属性添加验证"""
    
    def __new__(mcs, name, bases, namespace):
        annotations = namespace.get('__annotations__', {})
        
        original_init = namespace.get('__init__')
        
        def new_init(self, **kwargs):
            for key, expected_type in annotations.items():
                if key in kwargs:
                    value = kwargs[key]
                    if not isinstance(value, expected_type):
                        raise TypeError(
                            f"{name}.{key} 期望 {expected_type.__name__}, "
                            f"实际得到 {type(value).__name__}"
                        )
                    setattr(self, key, value)
            if original_init:
                original_init(self, **kwargs)
        
        namespace['__init__'] = new_init
        return super().__new__(mcs, name, bases, namespace)

class User(metaclass=TypedMeta):
    name: str
    age: int
    
    def greet(self):
        return f"我是 {self.name}，{self.age} 岁"

user = User(name="Alice", age=25)
print(user.greet())
# user = User(name="Bob", age="30")  # TypeError!
```

### 常见面试题

**Q1：`__new__` 和 `__init__` 在元类中的区别是什么？**

A：在元类中，`__new__` 负责创建类对象本身（返回一个新的类），而 `__init__` 负责初始化已创建的类对象。`__new__` 在对象创建之前调用，用于控制对象的创建过程（如修改命名空间、改变基类等），必须返回一个实例（类对象）；`__init__` 在对象创建之后调用，用于初始化操作（如添加类属性、注册类等），不需要返回值。类比于普通类：`__new__` 创建类的实例（对象），元类的 `__new__` 创建类的"实例"（类本身）。

**Q2：Python 中 `type` 和 `object` 的关系是什么？**

A：`type` 和 `object` 是 Python 对象模型的两个基石，它们形成了一个循环依赖：
1. `type` 是 `object` 的子类：`type(object)` 返回 `type`，即 `object` 是 `type` 的实例。
2. `object` 是 `type` 的基类：`type.__bases__` 是 `(object,)`。
3. `type` 是自身的实例：`type(type)` 返回 `type`。
可以用一句话总结：**`type` 是 `object` 的子类，`object` 是 `type` 的实例**。这个设计使得 Python 的类型系统既一致又完整——所有东西都是对象（继承自 `object`），所有类型都是 `type` 的实例。

---

## 6. 魔术方法（Magic Methods / Dunder Methods）

### 概念解释

魔术方法（Magic Methods），也称为双下划线方法（Dunder Methods，即 Double UNDERscore），是 Python 中一类以双下划线开头和结尾的特殊方法。它们不是设计给用户直接调用的，而是由 Python 解释器在特定场景下自动触发。掌握魔术方法是写出"Pythonic"代码的关键。

**对象创建与初始化**：
- `__new__(cls, *args, **kwargs)`：类的构造方法，负责创建并返回实例。它是真正的"构造函数"，在 `__init__` 之前调用。`__new__` 是一个类方法（接收 `cls`），通常返回 `cls` 的实例。单例模式、不可变子类化等高级用法都需要重写 `__new__`。
- `__init__(self, *args, **kwargs)`：初始化方法，在实例创建后调用，用于设置初始状态。绝大多数类只需要重写 `__init__`。

**可调用对象**：
- `__call__(self, *args, **kwargs)`：让实例可以像函数一样被调用。常用于创建闭包替代方案、策略模式、装饰器类。

**属性访问**：
- `__getattr__(self, name)`：当访问不存在的属性时触发。常用于实现动态属性、代理模式、延迟加载。
- `__getattribute__(self, name)`：访问任何属性时都会触发，优先级高于 `__getattr__`。使用时需格外小心，避免无限递归。
- `__setattr__(self, name, value)`：设置属性时触发。
- `__delattr__(self, name)`：删除属性时触发。

**描述符协议**（未在本节展开，但相关）：`__get__`、`__set__`、`__delete__`。

**内存优化**：
- `__slots__`：类属性，用元组声明实例允许拥有的属性名。使用 `__slots__` 后，实例不再使用 `__dict__` 存储属性，而是使用固定大小的数组，显著节省内存（约 40%-50%），并加快属性访问速度。副作用是实例不能再动态添加新属性。

### 代码示例

```python
# ================ __new__ vs __init__ ================
class LimitedInstance:
    """限制最多只能创建3个实例"""
    _count = 0
    _max = 3
    _pool = []
    
    def __new__(cls, *args, **kwargs):
        if cls._count < cls._max:
            instance = super().__new__(cls)
            cls._count += 1
            cls._pool.append(instance)
            return instance
        # 超过限制时，复用最老的实例
        return cls._pool[cls._count % cls._max]
    
    def __init__(self, name):
        self.name = name
        print(f"初始化: {name}")

a = LimitedInstance("A")
b = LimitedInstance("B")
c = LimitedInstance("C")
d = LimitedInstance("D")  # 复用 a 的实例
print(f"a is d: {a is d}")  # True

# ================ __call__ ================
class Counter:
    """可调用对象：每次调用计数加1"""
    def __init__(self, start=0):
        self.count = start
    
    def __call__(self, step=1):
        self.count += step
        return self.count

counter = Counter(10)
print(counter())      # 11
print(counter())      # 12
print(counter(5))     # 17

# ================ __getattr__ 与动态属性 ================
class LazyObject:
    """懒加载对象：只在访问时才创建属性"""
    def __init__(self):
        self._cache = {}
    
    def __getattr__(self, name):
        print(f"懒加载属性: {name}")
        if name.startswith('load_'):
            # 模拟耗时的加载操作
            value = f"{name} 的数据"
            self._cache[name] = value
            return value
        raise AttributeError(f"'{self.__class__.__name__}' 对象没有 '{name}' 属性")
    
    def __getattribute__(self, name):
        # 优先从缓存获取
        cache = object.__getattribute__(self, '_cache')
        if name in cache:
            print(f"从缓存获取: {name}")
            return cache[name]
        return object.__getattribute__(self, name)

obj = LazyObject()
print(obj.load_user)    # 懒加载属性: load_user
print(obj.load_user)    # 从缓存获取: load_user

# ================ __slots__ 内存优化 ================
import sys

class RegularPoint:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class SlotPoint:
    __slots__ = ('x', 'y')  # 声明允许的属性
    
    def __init__(self, x, y):
        self.x = x
        self.y = y

regular = RegularPoint(1, 2)
slot = SlotPoint(1, 2)

print(f"RegularPoint 实例大小: {sys.getsizeof(regular)} 字节")
print(f"SlotPoint 实例大小: {sys.getsizeof(slot)} 字节")

# slot.z = 3  # AttributeError: 'SlotPoint' 对象没有属性 'z'

# ================ 综合示例：Pythonic 的数值类 ================
class Vector:
    """支持算术运算的向量类"""
    __slots__ = ('x', 'y')
    
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __repr__(self):
        return f"Vector({self.x}, {self.y})"
    
    def __add__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x + other.x, self.y + other.y)
        return NotImplemented
    
    def __sub__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x - other.x, self.y - other.y)
        return NotImplemented
    
    def __mul__(self, scalar):
        if isinstance(scalar, (int, float)):
            return Vector(self.x * scalar, self.y * scalar)
        return NotImplemented
    
    def __rmul__(self, scalar):
        return self * scalar  # 支持 3 * vector
    
    def __abs__(self):
        return (self.x ** 2 + self.y ** 2) ** 0.5
    
    def __eq__(self, other):
        if isinstance(other, Vector):
            return self.x == other.x and self.y == other.y
        return NotImplemented
    
    def __bool__(self):
        return bool(abs(self))

v1 = Vector(3, 4)
v2 = Vector(1, 2)
print(f"v1 + v2 = {v1 + v2}")      # Vector(4, 6)
print(f"v1 * 2 = {v1 * 2}")         # Vector(6, 8)
print(f"3 * v1 = {3 * v1}")         # Vector(9, 12)
print(f"|v1| = {abs(v1)}")          # 5.0
print(f"v1 == Vector(3, 4): {v1 == Vector(3, 4)}")  # True
```

### 常见面试题

**Q1：`__new__` 和 `__init__` 的区别是什么？分别什么时候用？**

A：`__new__` 是类级别的构造方法（类方法，虽然不需要 `@classmethod` 装饰器），负责创建并返回实例对象，在实例存在之前执行。`__init__` 是实例级别的初始化方法，在实例创建后调用，负责设置实例的初始状态。使用场景：绝大多数情况只需重写 `__init__`；只有需要控制实例创建过程时才重写 `__new__`，如实现单例模式、返回其他类的实例、继承不可变类型（如 `int`、`str`、`tuple`）时。`__new__` 必须返回一个实例（通常调用 `super().__new__(cls)`），而 `__init__` 不需要返回值。

**Q2：`__getattr__` 和 `__getattribute__` 有什么区别？**

A：`__getattribute__` 在访问**任何属性**时都会被调用，优先级最高；`__getattr__` 只在访问**不存在的属性**时才会被调用（作为后备机制）。实现 `__getattribute__` 时必须通过 `object.__getattribute__(self, name)` 来获取属性，否则会陷入无限递归。`__getattr__` 相对安全，常用于代理模式和动态属性；`__getattribute__` 更强大但风险更高，通常只在框架开发中使用。

---

## 7. 上下文管理器（with 语句）

### 概念解释

上下文管理器（Context Manager）是 Python 中管理资源（文件、锁、网络连接、数据库事务等）的核心机制。它通过 `with` 语句确保资源在使用完毕后被正确释放，无论代码块是正常结束还是因异常而退出。这种"确保清理"的语义让代码更加健壮和安全。

上下文管理器基于**上下文管理协议**，要求对象实现两个魔术方法：
- `__enter__(self)`：进入上下文时调用，返回值会被绑定到 `as` 后的变量。
- `__exit__(self, exc_type, exc_val, exc_tb)`：退出上下文时调用，接收异常信息（无异常时均为 `None`）。如果返回 `True`，会抑制异常不向外部传播。

`with` 语句的执行流程：
1. 调用上下文管理器的 `__enter__()` 方法。
2. 将 `__enter__` 的返回值赋给 `as` 后的变量（如果有）。
3. 执行 `with` 语句体。
4. 无论是否发生异常，都调用 `__exit__()` 方法。
5. 如果发生异常，将异常信息传给 `__exit__`；如果 `__exit__` 返回 `True`，异常被吞掉；否则异常继续向外传播。

`contextlib` 模块提供了便捷的上下文管理器创建方式：
- `@contextmanager` 装饰器：让生成器函数变成上下文管理器，`yield` 之前的代码等价于 `__enter__`，`yield` 之后的代码等价于 `__exit__`。
- `closing()`：确保对象的 `close()` 方法被调用。
- `suppress(*exceptions)`：抑制指定的异常。

### 代码示例

```python
from contextlib import contextmanager
import time

# ================ 自定义上下文管理器类 ================
class DatabaseConnection:
    """数据库连接上下文管理器"""
    def __init__(self, dsn):
        self.dsn = dsn
        self.connection = None
    
    def __enter__(self):
        print(f"[DB] 连接到: {self.dsn}")
        self.connection = f"conn-{self.dsn}"
        return self.connection
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"[DB] 关闭连接: {self.connection}")
        self.connection = None
        # 返回 False，不抑制异常
        return False

with DatabaseConnection("postgresql://localhost") as conn:
    print(f"使用连接: {conn}")

# ================ @contextmanager 装饰器 ================
@contextmanager
def managed_file(filename, mode='r'):
    """文件上下文管理器"""
    print(f"[FILE] 打开: {filename}")
    f = open(filename, mode, encoding='utf-8')
    try:
        yield f  # yield 的值会被 as 捕获
    finally:
        print(f"[FILE] 关闭: {filename}")
        f.close()

# 测试文件
test_file = r"C:\Users\arthur\Documents\kimi\workspace\test.txt"
with open(test_file, 'w', encoding='utf-8') as f:
    f.write("Hello, Context Manager!")

with managed_file(test_file) as f:
    content = f.read()
    print(f"内容: {content}")

# ================ 计时上下文管理器 ================
@contextmanager
def timer(name="操作"):
    """计算代码块执行时间"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"[TIMER] {name} 耗时: {elapsed:.4f} 秒")

with timer("复杂计算"):
    total = sum(i ** 2 for i in range(1000000))
    print(f"计算结果: {total}")

# ================ 临时修改环境 ================
@contextmanager
def temporary_attribute(obj, attr, value):
    """临时修改对象属性，退出时恢复"""
    old_value = getattr(obj, attr, None)
    setattr(obj, attr, value)
    try:
        yield
    finally:
        if old_value is None:
            delattr(obj, attr)
        else:
            setattr(obj, attr, old_value)

class Config:
    debug = False

cfg = Config()
print(f"修改前: debug={cfg.debug}")
with temporary_attribute(cfg, 'debug', True):
    print(f"临时修改: debug={cfg.debug}")
print(f"恢复后: debug={cfg.debug}")

# ================ 嵌套上下文管理器 ================
@contextmanager
def transaction(db_name):
    print(f"[TX] 开始事务: {db_name}")
    try:
        yield db_name
        print(f"[TX] 提交事务: {db_name}")
    except Exception:
        print(f"[TX] 回滚事务: {db_name}")
        raise

@contextmanager
def lock(resource):
    print(f"[LOCK] 获取锁: {resource}")
    try:
        yield
    finally:
        print(f"[LOCK] 释放锁: {resource}")

# Python 3.10+ 支持括号分组
with (
    DatabaseConnection("db1") as conn1,
    transaction("orders") as tx,
    lock("user_table")
):
    print(f"执行操作: {conn1}, {tx}")

# ================ 实际应用：重试机制 ================
from contextlib import contextmanager
import random

@contextmanager
def retry_on_error(max_retries=3, exceptions=(Exception,)):
    """自动重试的上下文管理器"""
    for attempt in range(max_retries):
        try:
            yield attempt + 1
            break  # 成功则退出
        except exceptions as e:
            print(f"第 {attempt + 1} 次尝试失败: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1)

def flaky_operation():
    if random.random() < 0.7:  # 70% 概率失败
        raise ConnectionError("连接失败")
    return "成功"

# 使用示例（注意：retry_on_error 配合函数需要调整模式）
# 更实用的重试装饰器
```

### 常见面试题

**Q1：`with` 语句的底层原理是什么？`__exit__` 方法的三个参数分别是什么？**

A：`with` 语句的底层通过 `contextlib` 的上下文管理协议实现。Python 首先调用 `__enter__()` 获取资源，将其绑定到 `as` 变量；然后执行 `with` 块；最后确保调用 `__exit__(exc_type, exc_val, exc_tb)`。`__exit__` 的三个参数分别是：异常类型（`exc_type`）、异常值（`exc_val`）、异常追踪对象（`exc_tb`）。如果没有异常发生，这三个参数都是 `None`。如果 `__exit__` 返回 `True`，表示异常已被处理，不会向外传播；返回 `False` 或 `None`（默认），异常会继续传播。

**Q2：`@contextmanager` 装饰器的 `yield` 和生成器的 `yield` 有什么异同？**

A：在 `@contextmanager` 中，`yield` 之前的代码等价于 `__enter__`，`yield` 之后的代码（通常在 `finally` 块中）等价于 `__exit__`。它和生成器中的 `yield` 底层机制相同——都是暂停执行、保存状态、返回值。但语义上不同：生成器用于产出序列值，而 `@contextmanager` 中的 `yield` 用于划分资源获取和释放的边界。`yield` 的值会成为 `with ... as` 变量绑定的值。如果在 `with` 块中发生异常，异常会被注入到生成器中，在 `yield` 处抛出，这就是为什么 `yield` 后的代码通常要放在 `try...finally` 中以确保清理逻辑被执行。

---

## 8. 多继承与 MRO（方法解析顺序）

### 概念解释

Python 支持多继承，一个类可以同时继承多个父类。多继承虽然强大，但也带来了"菱形继承"（Diamond Problem）等复杂性——当多个父类有同名方法时，Python 需要一套规则来决定调用哪个。这套规则就是 **MRO（Method Resolution Order，方法解析顺序）**。

Python 2.2 之前使用深度优先的 MRO，但无法正确处理菱形继承。Python 2.3 引入了 **C3 线性化算法**（C3 Linearization），这是一种更复杂的排序算法，确保：
1. **子类优先于父类**：子类的方法总是覆盖父类。
2. **单调性**：如果一个类的 MRO 中 A 在 B 之前，那么在所有子类的 MRO 中 A 也在 B 之前（除非有覆盖）。
3. **局部优先**：局部声明的类优先于父类中声明的类。

C3 算法的核心思想：类的 MRO 是其父类 MRO 列表和父类列表的合并结果。公式为：
```
L(C(B1, B2, ..., Bn)) = C + merge(L(B1), L(B2), ..., L(Bn), B1, B2, ..., Bn)
```

通过类的 `__mro__` 属性可以查看方法解析顺序，`super()` 函数则按照 MRO 来查找下一个类。

`super()` 不是简单地调用父类方法，而是按照 MRO 调用下一个类的方法。这是实现协作式多重继承的关键——每个类只负责自己的行为，将其他行为委托给 MRO 中的下一个类。

### 代码示例

```python
# ================ MRO 基础演示 ================
class A:
    def method(self):
        print("A.method")

class B(A):
    def method(self):
        print("B.method")
        super().method()

class C(A):
    def method(self):
        print("C.method")
        super().method()

class D(B, C):
    def method(self):
        print("D.method")
        super().method()

# 查看 MRO
print(f"D.__mro__: {D.__mro__}")
# 输出: (<class 'D'>, <class 'B'>, <class 'C'>, <class 'A'>, <class 'object'>)

d = D()
d.method()
# 输出:
# D.method
# B.method
# C.method
# A.method

# ================ 菱形继承问题 ================
class Base:
    def __init__(self):
        self.base_attr = "base"
        print("Base.__init__")

class Left(Base):
    def __init__(self):
        super().__init__()
        self.left_attr = "left"
        print("Left.__init__")

class Right(Base):
    def __init__(self):
        super().__init__()
        self.right_attr = "right"
        print("Right.__init__")

class Bottom(Left, Right):
    def __init__(self):
        super().__init__()
        self.bottom_attr = "bottom"
        print("Bottom.__init__")

print(f"Bottom.__mro__: {Bottom.__mro__}")
b = Bottom()
# 输出:
# Base.__init__
# Right.__init__
# Left.__init__
# Bottom.__init__
# 注意：Base.__init__ 只被调用了一次！

# ================ super() 的本质 ================
class Parent:
    def __init__(self):
        print("Parent.__init__")

class Child1(Parent):
    def __init__(self):
        # super() 等价于 super(Child1, self)
        # 它按照 MRO 查找下一个类
        super().__init__()
        print("Child1.__init__")

class Child2(Parent):
    def __init__(self):
        super().__init__()
        print("Child2.__init__")

class GrandChild(Child1, Child2):
    def __init__(self):
        super().__init__()
        print("GrandChild.__init__")

gc = GrandChild()
print(f"GrandChild.__mro__: {GrandChild.__mro__}")
# MRO: GrandChild -> Child1 -> Child2 -> Parent -> object

# ================ 不使用 super() 的问题 ================
class BadLeft(Base):
    def __init__(self):
        Base.__init__(self)  # 硬编码调用父类！
        print("BadLeft.__init__")

class BadRight(Base):
    def __init__(self):
        Base.__init__(self)  # 硬编码调用父类！
        print("BadRight.__init__")

class BadBottom(BadLeft, BadRight):
    def __init__(self):
        BadLeft.__init__(self)
        BadRight.__init__(self)
        print("BadBottom.__init__")

print("--- 错误的菱形继承 ---")
bad = BadBottom()
# Base.__init__ 被调用了两次！这是菱形继承的问题

# ================ 混入模式（Mixin） ================
class JSONSerializableMixin:
    """混入类：为子类添加 JSON 序列化能力"""
    def to_json(self):
        import json
        # 只序列化公开属性
        data = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
        return json.dumps(data, ensure_ascii=False)

class TimestampMixin:
    """混入类：为子类添加时间戳功能"""
    from datetime import datetime
    
    def __init__(self):
        self.created_at = self.datetime.now().isoformat()
        super().__init__()

class User(JSONSerializableMixin, TimestampMixin):
    def __init__(self, name, age):
        super().__init__()  # 调用 TimestampMixin.__init__
        self.name = name
        self.age = age

user = User("Alice", 30)
print(user.to_json())
# {"created_at": "...", "name": "Alice", "age": 30}

# ================ C3 算法失败的案例 ================
try:
    class X:
        pass
    class Y:
        pass
    class Z(X, Y):
        pass
    class W(Y, X):
        pass
    # class Bad(Z, W):  # TypeError: MRO 不一致！
    #     pass
except TypeError as e:
    print(f"C3 拒绝不一致的继承: {e}")
```

### 常见面试题

**Q1：Python 的 MRO 是什么？C3 线性化算法的核心思想是什么？**

A：MRO（Method Resolution Order）是 Python 确定多继承中方法调用顺序的规则。Python 使用 C3 线性化算法来计算 MRO。核心思想是：
1. 子类总是在父类之前（保证覆盖语义）。
2. 如果子类继承多个父类，按照声明顺序查找。
3. 单调性：如果 A 在 B 前面出现在某个类的 MRO 中，那么在所有子类的 MRO 中 A 也应在 B 前面（除非被子类覆盖）。
4. C3 算法会拒绝不一致的继承关系（如 `class C(A, B)` 和 `class D(B, A)` 不能同时被继承）。
通过 `Class.__mro__` 或 `inspect.getmro(Class)` 可以查看 MRO。

**Q2：`super()` 不是调用父类方法，那它到底是做什么的？**

A：`super()` 调用的是 MRO 中当前类的**下一个类**的方法，而不一定是父类。`super(当前类, self)` 会从 MRO 中找到当前类的位置，然后调用其后的第一个类的方法。这是协作式多重继承的基石——每个类只关心自己在 MRO 中的下一个类，而不是硬编码父类。这种设计让多个不相关的类可以通过 MRO 协作工作（如混入模式），而不会出现菱形继承中基类被重复调用的问题。

---

## 9. 闭包与作用域（LEGB 规则）

### 概念解释

理解 Python 的作用域规则是编写正确代码的基础，也是面试中的高频考点。Python 使用 **LEGB 规则**来查找变量，这是四个作用域级别的首字母缩写：

1. **L - Local（局部作用域）**：当前函数内部定义的变量。
2. **E - Enclosing（嵌套作用域）**：外层（非全局）函数的变量，适用于嵌套函数。
3. **G - Global（全局作用域）**：模块级别定义的变量。
4. **B - Built-in（内置作用域）**：Python 内置的名称（如 `len`、`print`、`str` 等）。

查找顺序是 L → E → G → B。如果在所有作用域都找不到，抛出 `NameError`。

**闭包（Closure）**是指一个函数记住并访问其词法作用域（lexical scope）中的变量，即使这个函数在其词法作用域之外执行。闭包的形成需要三个条件：
1. 存在嵌套函数。
2. 内层函数引用了外层函数的变量。
3. 外层函数返回了内层函数（或以内层函数作为回调传递）。

闭包的核心价值在于**数据隐藏和状态保持**：可以创建"私有"变量，避免全局命名空间污染，同时保持状态跨多次调用。

**`global` 关键字**：在函数内部声明变量为全局变量，使得赋值操作修改的是全局作用域中的变量，而非创建局部变量。

**`nonlocal` 关键字**：在嵌套函数中声明变量为外层（非全局）函数的变量，使得内层函数可以修改外层函数的局部变量。`nonlocal` 是 Python 3 引入的，填补了 Python 2 中闭包只能读取不能修改外层变量的缺陷。

### 代码示例

```python
# ================ LEGB 规则演示 ================
name = "global"  # G - 全局作用域

def outer():
    name = "enclosing"  # E - 嵌套作用域
    
    def inner():
        name = "local"  # L - 局部作用域
        print(f"inner: {name}")  # local
    
    inner()
    print(f"outer: {name}")  # enclosing

outer()
print(f"global: {name}")  # global

# ================ 闭包基础 ================
def make_multiplier(n):
    """创建乘法器的工厂函数"""
    def multiplier(x):
        return x * n  # 引用了外层函数的变量 n
    return multiplier

times3 = make_multiplier(3)
times5 = make_multiplier(5)

print(f"times3(10) = {times3(10)}")  # 30
print(f"times5(10) = {times5(10)}")  # 50

# 每个闭包都保存了独立的 n 值
print(f"times3 的闭包变量: {times3.__closure__[0].cell_contents}")  # 3
print(f"times5 的闭包变量: {times5.__closure__[0].cell_contents}")  # 5

# ================ nonlocal 关键字 ================
def make_counter():
    """使用闭包实现计数器"""
    count = 0  # 外层函数的局部变量
    
    def counter():
        nonlocal count  # 声明使用外层变量，而非创建局部变量
        count += 1
        return count
    
    def reset():
        nonlocal count
        count = 0
    
    return counter, reset

counter, reset = make_counter()
print(f"counter() = {counter()}")  # 1
print(f"counter() = {counter()}")  # 2
print(f"counter() = {counter()}")  # 3
reset()
print(f"reset后 counter() = {counter()}")  # 1

# ================ global 关键字 ================
total = 0

def add_to_total(value):
    global total  # 声明使用全局变量
    total += value
    return total

print(f"add_to_total(10): {add_to_total(10)}")  # 10
print(f"add_to_total(20): {add_to_total(20)}")  # 30

# ================ 经典陷阱：闭包与循环变量 ================
def create_multipliers_wrong():
    """错误版本：所有闭包共享同一个循环变量"""
    return [lambda x: i * x for i in range(5)]

multipliers_wrong = create_multipliers_wrong()
print(f"错误版本: {[m(2) for m in multipliers_wrong]}")
# 输出: [8, 8, 8, 8, 8] — 全部使用了最后的 i=4！

# 修复方法1：默认参数
def create_multipliers_fixed1():
    return [lambda x, i=i: i * x for i in range(5)]

# 修复方法2：工厂函数
def make_multiplier_i(i):
    return lambda x: i * x

def create_multipliers_fixed2():
    return [make_multiplier_i(i) for i in range(5)]

print(f"修复版本1: {[m(2) for m in create_multipliers_fixed1()]}")
print(f"修复版本2: {[m(2) for m in create_multipliers_fixed2()]}")
# 输出: [0, 2, 4, 6, 8]

# ================ 装饰器与闭包 ================
def decorator_with_args(prefix):
    """带参数的装饰器——利用闭包保存参数"""
    def actual_decorator(func):
        def wrapper(*args, **kwargs):
            print(f"[{prefix}] 调用 {func.__name__}")
            return func(*args, **kwargs)
        return wrapper
    return actual_decorator

@decorator_with_args("DEBUG")
def hello():
    print("Hello!")

hello()

# ================ 使用闭包实现记忆化（Memoization） ================
def memoize(func):
    """函数结果缓存装饰器"""
    cache = {}  # 闭包中的缓存字典
    
    def wrapper(*args):
        if args not in cache:
            cache[args] = func(*args)
        return cache[args]
    
    wrapper.cache = cache  # 暴露缓存以便查看
    return wrapper

@memoize
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

print(f"fib(30) = {fibonacci(30)}")
print(f"缓存命中次数: {len(fibonacci.cache)}")
```

### 常见面试题

**Q1：Python 的 LEGB 规则是什么？请举例说明。**

A：LEGB 是 Python 查找变量的作用域顺序：Local（局部）→ Enclosing（嵌套/闭包）→ Global（全局）→ Built-in（内置）。当在函数中引用一个变量时，Python 会按照这个顺序依次查找：首先在当前函数内部（Local），然后在外层函数（Enclosing），再在模块全局作用域（Global），最后在内置命名空间（Built-in）。如果在所有作用域都找不到，抛出 `NameError`。`global` 和 `nonlocal` 关键字分别用于声明变量来自全局作用域和嵌套作用域，使得在局部作用域中对这些变量的赋值操作修改的是外部变量，而不是创建新的局部变量。

**Q2：以下代码的输出是什么？为什么？**

```python
def make_functions():
    flist = []
    for i in range(3):
        def f():
            return i
        flist.append(f)
    return flist

for f in make_functions():
    print(f())
```

A：输出是 `2 2 2`（三个 2），而不是 `0 1 2`。原因是闭包中的变量 `i` 不是按值捕获的，而是按引用捕获的。当 `f()` 实际执行时，循环已经结束，`i` 的值为 2，所以所有闭包都返回 2。修复方法是利用默认参数的早绑定特性：`def f(i=i): return i`，这样每个闭包就绑定了循环当时的 `i` 值。

---

## 10. 常用内置模块

### 概念解释

Python 标准库提供了大量高质量的内置模块，熟练掌握这些模块是区分初级和高级 Python 开发者的重要标志。面试中经常考察对 `collections`、`itertools`、`functools`、`contextlib` 的理解和使用场景。

**`collections` 模块**提供了额外的专用容器数据类型，补充了内置的 `dict`、`list`、`set` 和 `tuple`：
- `namedtuple`：创建带命名字段的元组子类，让元组可以通过名称访问，提高代码可读性。
- `deque`：双端队列，两端插入和删除都是 O(1)，适合实现队列和栈。
- `Counter`：字典子类，用于计数可哈希对象，自动处理计数的统计操作。
- `defaultdict`：带默认值的字典，访问不存在的键时自动创建默认值。
- `OrderedDict`：保持插入顺序的字典（Python 3.7+ 后普通 dict 也保持顺序，但 `OrderedDict` 仍有特殊方法如 `move_to_end`）。

**`itertools` 模块**提供了创建高效迭代器的工具，所有函数都是惰性求值，适合处理大数据：
- 无限迭代器：`count`、`cycle`、`repeat`。
- 组合迭代器：`product`（笛卡尔积）、`permutations`（排列）、`combinations`（组合）。
- 过滤和分组：`filterfalse`、`takewhile`、`dropwhile`、`groupby`。

**`functools` 模块**提供高阶函数和可调用对象操作：
- `lru_cache`：基于字典的最久未使用缓存装饰器，显著提升递归函数性能。
- `wraps`：装饰器辅助函数，保留被装饰函数的元数据。
- `partial`：偏函数，固定部分参数，生成新函数。
- `reduce`：累积计算，将二元函数应用于序列。
- `singledispatch`：泛型函数，根据第一个参数类型分派到不同实现。

**`contextlib` 模块**简化上下文管理器的创建，已在上一节详细介绍。

### 代码示例

```python
from collections import namedtuple, deque, Counter, defaultdict, OrderedDict
from itertools import count, cycle, permutations, combinations, groupby, chain
from functools import lru_cache, partial, reduce, wraps, singledispatch

# ================ collections ================

# namedtuple: 可读性更强的元组
Point = namedtuple('Point', ['x', 'y'])
p = Point(11, y=22)
print(f"Point: x={p.x}, y={p.y}")

# deque: 双端队列
queue = deque(maxlen=3)
queue.append(1)
queue.append(2)
queue.append(3)
queue.append(4)  # 自动移除最旧的 1
print(f"deque: {list(queue)}")  # [2, 3, 4]
queue.appendleft(0)
print(f"deque after appendleft: {list(queue)}")  # [0, 2, 3]

# Counter: 计数器
words = ['apple', 'banana', 'apple', 'cherry', 'banana', 'apple']
word_counts = Counter(words)
print(f"词频统计: {word_counts}")
print(f"最常见的: {word_counts.most_common(2)}")

# defaultdict: 带默认值的字典
word_groups = defaultdict(list)
for word in words:
    word_groups[word[0]].append(word)
print(f"按首字母分组: {dict(word_groups)}")

# ================ itertools ================

# count: 无限计数器
for i in count(10, 2):  # 从10开始，步长2
    if i > 20:
        break
    print(i, end=" ")
print()

# permutations/combinations
items = ['A', 'B', 'C']
print(f"排列 P(3,2): {list(permutations(items, 2))}")
print(f"组合 C(3,2): {list(combinations(items, 2))}")

# groupby: 按连续相同值分组（需要先排序）
data = [('apple', 'fruit'), ('banana', 'fruit'), ('carrot', 'vegetable'), ('date', 'fruit')]
data.sort(key=lambda x: x[1])
for category, group in groupby(data, key=lambda x: x[1]):
    items = list(group)
    print(f"{category}: {[item[0] for item in items]}")

# chain: 扁平化多个可迭代对象
list1 = [1, 2, 3]
list2 = ['a', 'b']
list3 = (True, False)
print(f"chain: {list(chain(list1, list2, list3))}")

# ================ functools ================

# lru_cache: 自动缓存
@lru_cache(maxsize=None)
def factorial(n):
    return 1 if n < 2 else n * factorial(n - 1)

print(f"factorial(5): {factorial(5)}")
print(f"缓存信息: {factorial.cache_info()}")

# partial: 偏函数
basetwo = partial(int, base=2)  # 固定 base=2
print(f"二进制转十进制: {basetwo('1010')}")  # 10

# reduce: 累积计算
numbers = [1, 2, 3, 4, 5]
product = reduce(lambda x, y: x * y, numbers)
print(f"乘积: {product}")  # 120

# singledispatch: 函数重载
@singledispatch
def process(arg):
    return f"默认处理: {arg}"

@process.register(int)
def _(arg):
    return f"整数处理: {arg * 2}"

@process.register(str)
def _(arg):
    return f"字符串处理: {arg.upper()}"

@process.register(list)
def _(arg):
    return f"列表处理: 长度={len(arg)}"

print(process(10))
print(process("hello"))
print(process([1, 2, 3]))

# ================ 实际应用：使用标准库解决实际问题 ================

# 问题：找到列表中出现频率最高的前 K 个元素
def top_k_frequent(nums, k):
    """利用 Counter 和 most_common"""
    return [num for num, _ in Counter(nums).most_common(k)]

print(f"前2个高频元素: {top_k_frequent([1,1,1,2,2,3], 2)}")

# 问题：实现滑动窗口最大值
from collections import deque

def max_sliding_window(nums, k):
    """使用 deque 实现 O(n) 滑动窗口最大值"""
    result = []
    dq = deque()  # 存储索引，保持递减顺序
    
    for i, num in enumerate(nums):
        # 移除窗口外的元素
        while dq and dq[0] <= i - k:
            dq.popleft()
        
        # 移除比当前元素小的所有元素（它们不可能成为最大值）
        while dq and nums[dq[-1]] < num:
            dq.pop()
        
        dq.append(i)
        
        # 从第 k-1 个元素开始记录结果
        if i >= k - 1:
            result.append(nums[dq[0]])
    
    return result

print(f"滑动窗口最大值: {max_sliding_window([1,3,-1,-3,5,3,6,7], 3)}")
```

### 常见面试题

**Q1：`collections.defaultdict` 和 `dict.get()` 的区别是什么？**

A：`defaultdict` 在访问不存在的键时会自动调用工厂函数创建默认值并插入字典；而 `dict.get(key, default)` 只是返回默认值，不会修改原字典。`defaultdict` 适用于需要构建分组、聚合等场景（如 `word_groups[char].append(word)`），避免繁琐的 `if char not in word_groups: word_groups[char] = []` 判断。但需要注意，`defaultdict` 会在每次访问缺失键时创建默认值，如果不希望修改字典，应使用 `dict.get()` 或 `try...except KeyError`。

**Q2：`functools.lru_cache` 的原理是什么？使用时有何注意事项？**

A：`lru_cache` 是一个装饰器，内部使用有序字典（或类似结构）来缓存函数调用的结果。键是函数参数（必须可哈希），值是函数返回值。当缓存达到 `maxsize` 时，最久未使用的条目被淘汰。注意事项：
1. 被装饰函数的参数必须可哈希（因为用作字典键）。
2. 函数应该是"纯函数"——相同输入总是产生相同输出，没有副作用。
3. 对于占用内存大的返回值，要谨慎设置 `maxsize`。
4. 可以使用 `typed=True` 让不同类型但值相等的参数（如 `1` 和 `1.0`）分别缓存。
5. 通过 `cache_info()` 查看命中/未命中统计，`cache_clear()` 清空缓存。

---

## 11. 类型注解与类型检查

### 概念解释

Python 是动态类型语言，但在大型项目和团队协作中，类型信息能显著提高代码的可读性、可维护性和 IDE 的智能提示能力。PEP 484（Type Hints）引入的类型注解系统是 Python 现代开发的重要基础设施。

**基本类型注解**：使用 `: Type` 标注变量和参数类型，`-> Type` 标注返回值类型。这些注解在运行时完全不影响程序行为，仅用于静态类型检查和 IDE 提示。Python 不会在运行时强制类型。

**`typing` 模块**提供了丰富的类型构造工具：
- `List[T]`、`Dict[K, V]`、`Set[T]`、`Tuple[T, ...]`、`Optional[T]`、`Union[T1, T2]` 等泛型容器。
- `Callable[[ArgType], ReturnType]`：可调用对象类型。
- `Any`：任意类型，用于逐步迁移或无法确定类型的情况。
- `Protocol`（PEP 544）：结构子类型（鸭子类型的正式化），定义接口而不需要显式继承。
- `Generic[T]`、`TypeVar`：自定义泛型类和类型变量。
- `TypedDict`：带类型提示的字典。

**静态类型检查工具**：
- **mypy**：最流行的 Python 静态类型检查器，能捕获类型错误、推断类型、检查泛型约束。
- **pyright**：微软开发的类型检查器，集成在 Pylance 中，速度快、对 PEP 兼容性高。
- **pytype**：Google 开发的类型检查器，支持类型推断。

类型注解的**核心价值**不在于运行时的类型安全（Python 不强制），而在于开发阶段的错误预防和代码文档化。

### 代码示例

```python
from typing import (
    List, Dict, Set, Tuple, Optional, Union, 
    Callable, Any, Protocol, Generic, TypeVar, TypedDict
)
from dataclasses import dataclass
from decimal import Decimal

# ================ 基础类型注解 ================
def greet(name: str, times: int = 1) -> str:
    """带类型注解的函数"""
    return (f"Hello, {name}!\n") * times

def process_data(data: List[int]) -> Dict[str, int]:
    """列表参数，字典返回值"""
    return {"sum": sum(data), "count": len(data)}

# Optional: 可能为 None 的值
def find_user(user_id: int) -> Optional[Dict[str, Any]]:
    users = {1: {"name": "Alice"}, 2: {"name": "Bob"}}
    return users.get(user_id)

# Union: 多种可能的类型
def parse_value(value: Union[str, int, float]) -> float:
    return float(value)

# ================ Protocol（结构子类型 / 鸭子类型） ================
class Drawable(Protocol):
    """定义 Drawable 协议：任何有 draw 方法的对象都符合"""
    def draw(self) -> None:
        ...

def render(item: Drawable) -> None:
    """接受任何实现了 draw 方法的对象，不需要显式继承 Drawable"""
    item.draw()

class Circle:
    def draw(self) -> None:
        print("画一个圆")

class Square:
    def draw(self) -> None:
        print("画一个正方形")

# Circle 和 Square 都没有继承 Drawable，但满足协议
render(Circle())
render(Square())

# ================ 泛型 ================
T = TypeVar('T')  # 定义类型变量
K = TypeVar('K')
V = TypeVar('V')

class Stack(Generic[T]):
    """泛型栈"""
    def __init__(self) -> None:
        self._items: List[T] = []
    
    def push(self, item: T) -> None:
        self._items.append(item)
    
    def pop(self) -> Optional[T]:
        return self._items.pop() if self._items else None
    
    def peek(self) -> Optional[T]:
        return self._items[-1] if self._items else None

int_stack = Stack[int]()
int_stack.push(1)
int_stack.push(2)
print(f"栈顶: {int_stack.pop()}")

# ================ TypedDict ================
class Movie(TypedDict):
    name: str
    year: int
    rating: float

movie: Movie = {"name": "Inception", "year": 2010, "rating": 8.8}

# ================ 可调用类型 ================
BinaryOp = Callable[[int, int], int]

def apply_op(a: int, b: int, op: BinaryOp) -> int:
    return op(a, b)

print(f"apply_op(3, 4, lambda x,y: x+y): {apply_op(3, 4, lambda x, y: x + y)}")

# ================ 重载（Overloads） ================
from typing import overload

@overload
def add(x: int, y: int) -> int: ...

@overload
def add(x: str, y: str) -> str: ...

def add(x: Union[int, str], y: Union[int, str]) -> Union[int, str]:
    return x + y  # type: ignore

print(add(1, 2))       # 3
print(add("a", "b"))   # "ab"

# ================ dataclass 结合类型注解 ================
@dataclass(frozen=True)
class Product:
    name: str
    price: Decimal
    quantity: int
    
    @property
    def total_value(self) -> Decimal:
        return self.price * self.quantity

product = Product(name="Laptop", price=Decimal("999.99"), quantity=2)
print(f"商品总价值: {product.total_value()}")

# ================ 类型别名 ================
Vector = List[float]
Matrix = List[Vector]
UserID = int

def scale_vector(v: Vector, scalar: float) -> Vector:
    return [x * scalar for x in v]

v: Vector = [1.0, 2.0, 3.0]
print(f"缩放后: {scale_vector(v, 2.0)}")
```

### 常见面试题

**Q1：Python 的类型注解在运行时会生效吗？如果不生效，它的价值在哪里？**

A：Python 的类型注解在运行时**完全不生效**——它们被存储在 `__annotations__` 字典中，但解释器不会进行任何类型检查。类型注解的价值主要体现在：
1. **静态类型检查**：通过 mypy、pyright 等工具在开发阶段发现类型错误。
2. **IDE 智能提示**：提供代码补全、参数提示、跳转定义等功能。
3. **代码即文档**：类型签名本身就是清晰的接口文档。
4. **重构安全**：大型项目重构时，类型检查器能捕获大量潜在错误。
5. **设计辅助**：编写类型注解强迫开发者思考接口契约，提升设计质量。

**Q2：`Protocol` 和抽象基类（ABC）有什么区别？**

A：`Protocol` 属于**结构子类型（Structural Subtyping）**，一个类只要实现了 Protocol 定义的方法，就被认为符合该 Protocol，不需要显式声明继承。ABC 属于**名义子类型（Nominal Subtyping）**，类必须显式继承 ABC（或注册为虚拟子类）才算其子类。`Protocol` 更适合鸭子类型的场景，让代码更灵活；ABC 更严格，适合需要强制继承关系的框架设计。`Protocol` 是 PEP 544 引入的，在静态类型检查时使用，运行时开销极小。

---

## 12. 异常处理机制与最佳实践

### 概念解释

异常处理是编写健壮程序的核心技能。Python 的异常机制基于**栈展开（Stack Unwinding）**：当异常发生时，解释器会在当前执行栈中逐层查找匹配的 `except` 子句，如果找到则执行处理代码，否则继续向外层传播，直到被处理或导致程序终止。

**异常层次结构**：Python 内置异常都继承自 `BaseException`，用户自定义异常应继承自 `Exception`（而非 `BaseException`，因为 `KeyboardInterrupt` 和 `SystemExit` 也继承自 `BaseException`，通常不应捕获）。常用内置异常包括：
- `ValueError`：传入值类型正确但内容不合法。
- `TypeError`：传入值类型不正确。
- `KeyError`：字典中键不存在。
- `IndexError`：序列索引越界。
- `AttributeError`：访问不存在的属性。
- `IOError`/`OSError`：I/O 操作失败。
- `RuntimeError`：通用运行时错误。

**最佳实践**：
1. **具体捕获**：尽量捕获具体的异常类型，而非裸 `except:` 或 `except Exception:`。
2. **不要吞掉异常**：`except` 块中至少应记录日志，空 `pass` 是反模式。
3. **异常是异常情况**：不要用异常处理控制正常流程（不要用 `try/except` 做 `if/else` 该做的事）。
4. **自定义异常**：为模块/应用定义异常层次结构，继承自 `Exception` 或更具体的类型。
5. **异常链**：使用 `raise ... from e` 保留原始异常上下文。
6. **上下文管理器**：使用 `with` 语句确保资源释放，即使在异常情况下。

**`else` 和 `finally` 子句**：
- `else`：在 `try` 块**没有发生异常**时执行，适合放正常流程代码。
- `finally`：**无论是否发生异常**都执行，适合资源清理。

### 代码示例

```python
import logging
from typing import Optional

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================ 自定义异常层次结构 ================
class ApplicationError(Exception):
    """应用基础异常"""
    pass

class ValidationError(ApplicationError):
    """数据验证失败"""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"字段 '{field}' 验证失败: {message}")

class ResourceNotFoundError(ApplicationError):
    """资源不存在"""
    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} '{resource_id}' 不存在")

# ================ 异常处理最佳实践 ================
def divide_numbers(a: float, b: float) -> Optional[float]:
    """安全除法"""
    try:
        result = a / b
    except ZeroDivisionError as e:
        # 1. 记录日志
        logger.error(f"除零错误: a={a}, b={b}")
        # 2. 不吞掉信息，重新抛出或返回 None
        return None
    except TypeError as e:
        # 3. 异常链：保留原始上下文
        raise ValidationError("参数", f"必须是数字，收到: {type(a)}, {type(b)}") from e
    else:
        # 4. try 块成功执行后才运行
        logger.info(f"计算成功: {a} / {b} = {result}")
        return result
    finally:
        # 5. 无论成功与否都执行
        print("除法操作完成")

print(divide_numbers(10, 2))   # 5.0
print(divide_numbers(10, 0))   # None

# ================ 上下文管理器处理异常 ================
class DatabaseTransaction:
    """自动事务管理"""
    def __init__(self, db):
        self.db = db
    
    def __enter__(self):
        print("[TX] 开始事务")
        return self.db
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            print("[TX] 提交事务")
        else:
            print(f"[TX] 回滚事务 (错误: {exc_val})")
            # 返回 False 让异常继续传播
            return False

# ================ 不要用异常做流程控制 ================
# ❌ 反模式：用异常检查键是否存在
def bad_get_user(users, user_id):
    try:
        return users[user_id]
    except KeyError:
        return None

# ✅ 正确做法：用 dict.get()
def good_get_user(users, user_id):
    return users.get(user_id)

# ❌ 反模式：用异常检查文件是否存在
import os

def bad_read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""

# ✅ 正确做法：先检查

def good_read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read()

# ================ 异常分组处理（Python 3.11+ ExceptionGroup） ================
# 注：以下为示意代码，ExceptionGroup 需要 Python 3.11+
try:
    # 可能抛出多种异常
    pass
except* ValueError as eg:
    # 处理所有 ValueError
    for e in eg.exceptions:
        logger.error(f"值错误: {e}")
except* TypeError as eg:
    # 处理所有 TypeError
    for e in eg.exceptions:
        logger.error(f"类型错误: {e}")

# ================ 实用工具：重试装饰器 ================
from functools import wraps
import time
from typing import Type, Tuple

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """带重试机制的装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} 第 {attempt} 次尝试失败: {e}，"
                            f"{delay}秒后重试..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} 最终失败，已重试 {max_attempts} 次")
            raise last_exception
        return wrapper
    return decorator

@retry(max_attempts=3, delay=0.5, exceptions=(ConnectionError, TimeoutError))
def unstable_operation():
    """模拟不稳定的操作"""
    import random
    if random.random() < 0.7:
        raise ConnectionError("连接失败")
    return "成功"

# 由于随机性，这里不实际调用
# print(unstable_operation())

# ================ 断言的正确使用 ================
def calculate_discount(price: float, discount_rate: float) -> float:
    """计算折扣后价格"""
    # 断言用于检查程序员的假设（不变量），不应依赖它做输入验证
    assert price >= 0, f"价格不能为负: {price}"
    assert 0 <= discount_rate <= 1, f"折扣率必须在 0-1 之间: {discount_rate}"
    
    return price * (1 - discount_rate)

print(f"折扣后价格: {calculate_discount(100, 0.2)}")
# calculate_discount(-10, 0.2)  # AssertionError（仅在调试模式）
```

### 常见面试题

**Q1：`except:`、`except Exception:` 和 `except BaseException:` 有什么区别？**

A：
- `except:` 捕获所有继承自 `BaseException` 的异常，包括 `SystemExit`、`KeyboardInterrupt`、`GeneratorExit`，是最危险的写法，会拦截所有东西（包括程序退出信号）。
- `except Exception:` 捕获所有继承自 `Exception` 的异常，排除了 `SystemExit` 和 `KeyboardInterrupt`，但仍可能捕获过多异常。
- `except BaseException:` 显式捕获 `BaseException`，效果同裸 `except:`。

最佳实践是捕获**最具体的异常类型**，如 `except ValueError as e:`。如果确实需要捕获多个异常，使用元组：`except (ValueError, TypeError) as e:`。

**Q2：`try...finally` 中的 `finally` 块是否一定会执行？有没有例外情况？**

A：`finally` 块在**绝大多数情况**下都会执行，包括：
1. `try` 块正常完成。
2. `try` 块发生异常并被 `except` 处理。
3. `try` 块发生异常未被处理。
4. `try` 块中执行了 `return`、`break`、`continue`。

**唯一不执行 `finally` 的情况**是 Python 解释器本身被强制终止（如 `os._exit(0)`、`SIGKILL` 信号、系统崩溃）。另外，如果在 `finally` 块之前解释器进程被外部杀死（如 `kill -9`），`finally` 也不会执行。因此，`finally` 适用于常规的清理操作，但不能保证在极端情况下的绝对执行。

---

> **本章完**。掌握以上 12 个知识点，足以应对绝大多数 Python 后端面试中的基础部分。建议读者对每个知识点动手实验，并尝试在面试中结合项目经验进行阐述。




---


# 第 2 章：Vue 前端

> 本章系统梳理 Vue 生态核心技术栈，涵盖 Vue 2/3 核心差异、响应式原理、组件通信、路由管理、状态管理、性能优化及工程化实践等高频面试考点。每个知识点均配有原理剖析、可运行代码示例及经典面试题解析。

---

## 2.1 Vue 2 vs Vue 3 核心差异

Vue 3 于 2020 年 9 月正式发布，带来了大量架构层面的改进。理解两代版本的核心差异，是前端面试中最基础也最重要的考点之一。

**响应式系统的根本变革**是 Vue 2 与 Vue 3 最显著的差异。Vue 2 使用 `Object.defineProperty()` 遍历对象的所有属性进行劫持，这种方式存在明显局限：无法检测对象属性的新增和删除、无法监听数组索引的变化和 `length` 的修改。Vue 3 则采用 ES6 的 `Proxy` 对象对整个对象进行代理拦截，可以监听到属性的增删改查，支持数组索引和 `Map/Set/WeakMap/WeakSet` 等数据结构，响应式能力更加完备。

**API 设计范式的演进**是另一大核心差异。Vue 2 采用 Options API，将数据、方法、计算属性、生命周期等分散在不同的配置选项中。当组件逻辑复杂时，相关代码被迫分散在不同选项中，导致"选项碎片化"问题。Vue 3 引入了 Composition API，允许我们按照逻辑关注点组织代码，将相关的响应式状态、计算属性、方法等聚合在一起，极大地提升了代码的可维护性和复用性。`setup()` 函数是 Composition API 的入口，在组件创建之前执行。

**性能层面的全面提升**同样值得关注。Vue 3 的源码使用 TypeScript 重写，提供了更好的类型推断。编译器方面引入了静态提升（Static Hoisting）、Patch Flag 标记等优化策略，使得虚拟 DOM 的 Diff 过程更加高效。打包体积也大幅减小，核心运行时仅约 10KB（gzip）。

**新特性方面**，Vue 3 支持多根节点组件（Fragments）、Teleport（传送门）、Suspense（异步依赖处理）、全局 API 的修改（`createApp` 替代 `new Vue`）等。

```javascript
// ===== Vue 2 写法（Options API）=====
export default {
  data() {
    return {
      count: 0,
      user: { name: '张三' }
    }
  },
  computed: {
    doubleCount() {
      return this.count * 2
    }
  },
  methods: {
    increment() {
      this.count++
    }
  },
  mounted() {
    console.log('组件已挂载')
  }
}

// ===== Vue 3 写法（Composition API）=====
import { ref, computed, onMounted } from 'vue'

export default {
  setup() {
    // 响应式状态
    const count = ref(0)
    const user = reactive({ name: '张三' })
    
    // 计算属性
    const doubleCount = computed(() => count.value * 2)
    
    // 方法
    function increment() {
      count.value++
    }
    
    // 生命周期
    onMounted(() => {
      console.log('组件已挂载')
    })
    
    // 暴露给模板
    return { count, doubleCount, increment, user }
  }
}

// ===== Vue 3 语法糖 <script setup> =====
<script setup>
import { ref, computed, onMounted } from 'vue'

const count = ref(0)
const doubleCount = computed(() => count.value * 2)
function increment() { count.value++ }
onMounted(() => console.log('组件已挂载'))
</script>
```

### 常见面试题

**Q1: Vue 3 的响应式原理相比 Vue 2 有什么优势？**

> Vue 2 使用 `Object.defineProperty` 只能劫持已存在的属性，对于新增属性需要使用 `Vue.set` 或 `vm.$set`，删除属性需要用 `Vue.delete`。数组的变异方法（push、pop 等）虽然被重写，但直接通过索引修改或修改 length 无法触发响应式更新。Vue 3 的 `Proxy` 代理的是整个对象，天然支持属性的动态增删，也不需要对数组方法进行特殊重写，代码更简洁、行为更一致。此外，Vue 3 的响应式系统可以独立出来作为 `@vue/reactivity` 包使用，不再与 Vue 运行时强耦合。

**Q2: Composition API 相比 Options API 的优势是什么？适合什么场景？**

> `Composition API` 的核心优势在于逻辑复用和组织方式。在 Options API 中，一个功能的数据、计算属性、方法、监听器分散在不同的选项中，当组件有多个独立功能时，代码需要在选项间频繁跳转阅读。Composition API 允许按功能组织代码，将同一业务逻辑的代码聚合在一起，形成可复用的 Composable 函数。对于大型组件、逻辑复用需求高的场景（如多个组件共享相同的获取数据逻辑），Composition API 是更好的选择。但 Options API 对于简单组件和初学者更加直观，Vue 3 也完全兼容 Options API。

---

## 2.2 响应式系统（Proxy vs Object.defineProperty、ref/reactive/computed/watch）

响应式系统是 Vue 最核心的特性之一，也是面试中的高频考点。深入理解其实现原理，对排查响应式失效等问题至关重要。

### Proxy 与 Object.defineProperty 的原理对比

`Object.defineProperty` 是 ES5 的方法，它直接在对象上定义或修改属性，通过 `getter` 和 `setter` 拦截属性的读取和赋值操作。Vue 2 在初始化时遍历对象的每个属性，将其转换为 getter/setter。这种方式的缺陷在于：必须预先知道所有属性名，无法拦截新增属性；无法监听数组索引的变化（如 `arr[0] = 1`）；无法监听 `length` 属性的变化；嵌套对象需要递归处理，初始化性能开销大。

`Proxy` 是 ES6 引入的元编程特性，它可以创建一个对象的代理，拦截该对象的 13 种基本操作（包括 `get`、`set`、`deleteProperty`、`has`、`ownKeys` 等）。Vue 3 的响应式系统基于 `Proxy` 和 `Reflect` 实现。

```javascript
// ===== Vue 3 响应式核心简化版实现原理 =====
// 使用 WeakMap 存储依赖关系，避免内存泄漏
const targetMap = new WeakMap()
let activeEffect = null

function track(target, key) {
  if (!activeEffect) return
  let depsMap = targetMap.get(target)
  if (!depsMap) {
    targetMap.set(target, (depsMap = new Map()))
  }
  let dep = depsMap.get(key)
  if (!dep) {
    depsMap.set(key, (dep = new Set()))
  }
  dep.add(activeEffect)
}

function trigger(target, key) {
  const depsMap = targetMap.get(target)
  if (!depsMap) return
  const dep = depsMap.get(key)
  if (dep) {
    dep.forEach(effect => effect())
  }
}

function reactive(obj) {
  return new Proxy(obj, {
    get(target, key, receiver) {
      track(target, key)  // 收集依赖
      const result = Reflect.get(target, key, receiver)
      // 递归处理嵌套对象
      if (typeof result === 'object' && result !== null) {
        return reactive(result)
      }
      return result
    },
    set(target, key, value, receiver) {
      const oldValue = target[key]
      const result = Reflect.set(target, key, value, receiver)
      if (oldValue !== value) {
        trigger(target, key)  // 触发更新
      }
      return result
    },
    deleteProperty(target, key) {
      const hadKey = Object.prototype.hasOwnProperty.call(target, key)
      const result = Reflect.deleteProperty(target, key)
      if (hadKey && result) {
        trigger(target, key)
      }
      return result
    }
  })
}
```

### ref、reactive、computed、watch 的使用与区别

这四个 API 是 Vue 3 Composition API 中处理响应式状态的核心工具。`ref` 用于创建基本类型的响应式数据，返回一个带有 `.value` 属性的对象。`reactive` 用于创建对象的响应式代理。`computed` 用于创建计算属性，具有缓存特性。`watch` 用于侦听响应式数据的变化，执行副作用。

```vue
<template>
  <div class="demo">
    <p>计数: {{ count }}</p>
    <p>双倍计数: {{ doubleCount }}</p>
    <p>用户信息: {{ user.name }} - {{ user.age }}岁</p>
    <p>全名: {{ fullName }}</p>
    <button @click="increment">增加</button>
    <button @click="updateUser">更新用户</button>
    <button @click="changeName">改名</button>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'

// ref：基本类型的响应式引用
const count = ref(0)

// reactive：对象的响应式代理
const user = reactive({
  name: '张三',
  age: 25,
  address: { city: '北京' }
})

// computed：计算属性（有缓存）
const doubleCount = computed(() => count.value * 2)

// computed 也支持 setter
const fullName = computed({
  get() {
    return user.name + '（' + user.age + '岁）'
  },
  set(newValue) {
    user.name = newValue.split('（')[0]
  }
})

// watch：侦听器
watch(count, (newVal, oldVal) => {
  console.log(`count 变化: ${oldVal} -> ${newVal}`)
})

// 侦听 reactive 对象的属性（使用 getter 函数）
watch(() => user.age, (newVal, oldVal) => {
  console.log(`年龄变化: ${oldVal} -> ${newVal}`)
})

// 侦听多个源
watch([count, () => user.name], ([newCount, newName]) => {
  console.log('多个源变化:', { newCount, newName })
})

// 立即执行 + 深度监听
watch(() => user.address, (newVal) => {
  console.log('地址变化:', newVal)
}, { immediate: true, deep: true })

function increment() {
  count.value++  // ref 需要 .value
}

function updateUser() {
  user.age++  // reactive 对象直接修改
  user.gender = '男'  // Proxy 支持动态添加属性
}

function changeName() {
  user.name = user.name === '张三' ? '李四' : '张三'
}
</script>
```

### 常见面试题

**Q1: ref 和 reactive 的区别是什么？什么时候用 ref，什么时候用 reactive？**

> `ref` 可以包装任意类型的值（原始类型和对象都可以），返回的对象需要通过 `.value` 访问内部值。`reactive` 只能用于对象类型，返回的代理对象可以直接访问属性。推荐的做法是：如果是基本类型（string、number、boolean）用 `ref`；如果是对象类型，两种都可以。Vue 官方建议统一使用 `ref`，因为它更灵活（可以重新赋值整个对象），在解构或作为参数传递时也不会丢失响应式。`reactive` 有一些限制：不能解构（会失去响应式），不能直接替换整个对象。

**Q2: computed 和 watch 的区别是什么？**

> `computed` 用于基于现有状态计算派生状态，具有缓存特性，只有当依赖变化时才重新计算，适合模板中展示的计算值。`computed` 应该是纯函数，不应该有副作用。`watch` 用于侦听数据变化并执行副作用（如发送请求、操作 DOM），没有缓存，每次数据变化都会执行回调。简单说：需要派生状态用 `computed`，需要执行副作用用 `watch`。

---

## 2.3 生命周期钩子（Vue2 vs Vue3 对照）

生命周期钩子是组件从创建到销毁过程中不同阶段触发的回调函数。理解生命周期有助于在正确的时机执行初始化、清理等操作。

### 生命周期阶段详解

Vue 组件的生命周期可以分为四个主要阶段：**创建**、**挂载**、**更新**、**卸载**。

- **创建阶段**：组件实例被初始化，但还没有挂载到 DOM 上。此时可以进行响应式数据的设置，但无法访问 DOM。
- **挂载阶段**：组件首次渲染到 DOM。此时可以访问 DOM 元素，适合执行需要 DOM 的操作（如图表初始化）。
- **更新阶段**：响应式数据变化导致组件重新渲染。可以在此阶段获取更新前后的 DOM 状态。
- **卸载阶段**：组件从 DOM 中移除。需要在此阶段清理副作用（如定时器、事件监听、WebSocket 连接），防止内存泄漏。

### Vue 2 与 Vue 3 生命周期对照表

| Vue 2 Options API | Vue 3 Options API | Vue 3 Composition API | 说明 |
|---|---|---|---|
| beforeCreate | beforeCreate | `setup()` | 实例初始化，响应式数据尚未设置 |
| created | created | `setup()` | 实例创建完成，可访问数据，但 DOM 未生成 |
| beforeMount | beforeMount | `onBeforeMount` | 挂载开始前，模板编译完成 |
| mounted | mounted | `onMounted` | 挂载完成，DOM 已可用 |
| beforeUpdate | beforeUpdate | `onBeforeUpdate` | 数据更新，DOM 重新渲染前 |
| updated | updated | `onUpdated` | DOM 更新完成 |
| beforeDestroy | **beforeUnmount** | `onBeforeUnmount` | 组件卸载前（Vue 3 更名） |
| destroyed | **unmounted** | `onUnmounted` | 组件卸载完成（Vue 3 更名） |
| errorCaptured | errorCaptured | `onErrorCaptured` | 子孙组件错误捕获 |
| - | - | `onRenderTracked` | 调试钩子：响应式依赖被追踪时 |
| - | - | `onRenderTriggered` | 调试钩子：响应式依赖触发重新渲染时 |

```vue
<template>
  <div ref="container">
    <p>{{ message }}</p>
    <button @click="updateMessage">更新消息</button>
  </div>
</template>

<script setup>
import { 
  ref, onBeforeMount, onMounted, 
  onBeforeUpdate, onUpdated, 
  onBeforeUnmount, onUnmounted 
} from 'vue'

const message = ref('Hello Vue 3')
const container = ref(null)
let timer = null

// 创建阶段：setup 本身就是创建阶段的入口
console.log('setup: 组件初始化')

// 挂载阶段
onBeforeMount(() => {
  console.log('onBeforeMount: DOM 即将挂载')
})

onMounted(() => {
  console.log('onMounted: DOM 已挂载', container.value)
  // 初始化定时器（副作用）
  timer = setInterval(() => {
    console.log('定时器运行中...')
  }, 5000)
})

// 更新阶段
onBeforeUpdate(() => {
  console.log('onBeforeUpdate: 组件即将更新')
})

onUpdated(() => {
  console.log('onUpdated: 组件更新完成')
})

// 卸载阶段：清理副作用至关重要
onBeforeUnmount(() => {
  console.log('onBeforeUnmount: 组件即将卸载')
})

onUnmounted(() => {
  console.log('onUnmounted: 组件已卸载')
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  // 其他清理：取消 API 请求、移除事件监听、关闭 WebSocket
})

function updateMessage() {
  message.value = '消息已更新: ' + new Date().toLocaleTimeString()
}
</script>
```

### 常见面试题

**Q1: Vue 3 的 setup 函数在哪个生命周期阶段执行？**

> `setup` 函数在组件的 `beforeCreate` 和 `created` 钩子之间执行。在 `setup` 内部，相当于同时替代了 Vue 2 的 `beforeCreate` 和 `created` 阶段。此时组件实例已创建，props 已解析，但 DOM 尚未挂载。因此 `setup` 中不要访问 DOM 相关的属性或方法。

**Q2: 为什么 Vue 3 将 beforeDestroy/destroyed 改名为 beforeUnmount/unmounted？**

> "destroy" 一词容易让人误解为实例被彻底销毁，但实际上 Vue 的组件实例在移除后仍然存在于内存中（等待垃圾回收）。"unmount"（卸载）更准确地描述了将组件从 DOM 树中移除的动作，同时提醒开发者需要在此阶段清理副作用。这与 React 的术语也保持了一致，降低了跨框架学习的心智负担。

---

## 2.4 组件通信方式（props/$emit、provide/inject、事件总线、Pinia/Vuex、mitt）

组件通信是 Vue 应用开发中不可避免的问题。随着应用规模的增长，组件之间的关系变得复杂，选择合适的通信方式至关重要。Vue 提供了多种通信机制，适用于不同场景。

### Props / $emit —— 父子组件通信

Props 向下传递数据，事件向上传递数据，这是 Vue 中最基本、最推荐的通信方式。父组件通过 props 向子组件传递数据，子组件通过 `$emit` 触发事件向父组件传递信息。

```vue
<!-- 子组件 Child.vue -->
<template>
  <div class="child">
    <p>接收到的消息: {{ message }}</p>
    <p>用户数: {{ userCount }}</p>
    <button @click="sendToParent">通知父组件</button>
  </div>
</template>

<script setup>
// 定义 props
const props = defineProps({
  message: {
    type: String,
    required: true,
    default: '默认消息'
  },
  userCount: {
    type: Number,
    validator: (value) => value >= 0
  }
})

// 定义 emit 事件
const emit = defineEmits(['update', 'delete'])

function sendToParent() {
  // 向父组件传递数据
  emit('update', { id: 1, content: '子组件的数据' })
  emit('delete', 1)
}
</script>

<!-- 父组件 Parent.vue -->
<template>
  <div class="parent">
    <Child 
      :message="parentMessage" 
      :user-count="10"
      @update="handleUpdate"
      @delete="handleDelete"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Child from './Child.vue'

const parentMessage = ref('来自父组件的问候')

function handleUpdate(data) {
  console.log('收到子组件更新:', data)
}

function handleDelete(id) {
  console.log('删除项目:', id)
}
</script>
```

### Provide / Inject —— 跨层级组件通信

当需要让祖父组件向深层嵌套的子孙组件传递数据时，逐层 props 传递会变得非常繁琐（"prop drilling"）。`provide` 和 `inject` 允许祖先组件作为依赖提供者，任何层级的后代组件都可以注入这些依赖。

```javascript
<!-- 祖先组件 App.vue -->
<script setup>
import { provide, ref, readonly } from 'vue'

// 提供响应式数据（建议用 readonly 防止后代直接修改）
const user = ref({ name: '张三', role: 'admin' })
const updateUser = (newUser) => { user.value = newUser }

provide('user', readonly(user))
provide('updateUser', updateUser)

// 也可以提供一个响应式对象，让后代可以修改
const theme = ref('light')
provide('theme', theme)
</script>

<!-- 深层子组件 DeepChild.vue -->
<script setup>
import { inject, computed } from 'vue'

// 注入依赖，可以设置默认值
const user = inject('user', { name: '游客' })
const updateUser = inject('updateUser')
const theme = inject('theme', ref('light'))

// 基于注入的数据创建计算属性
const displayName = computed(() => user.value?.name || '匿名')

function changeUser() {
  updateUser({ name: '李四', role: 'user' })
}
</script>
```

### mitt —— 轻量级事件总线

Vue 3 中移除了全局事件总线（`$on/$emit/$off`），推荐使用第三方库 mitt（仅 200 字节）来实现跨组件的事件通信。适合需要解耦的兄弟组件或任意组件间的通信场景。

```javascript
// ===== utils/eventBus.js =====
import mitt from 'mitt'
const emitter = mitt()
export default emitter

// ===== 组件 A：发送事件 =====
<template>
  <button @click="sendMessage">发送消息给 B</button>
</template>

<script setup>
import emitter from '@/utils/eventBus'

function sendMessage() {
  emitter.emit('message', { 
    from: '组件A', 
    content: '你好，组件B！',
    timestamp: Date.now()
  })
}
</script>

// ===== 组件 B：接收事件 =====
<script setup>
import { onMounted, onUnmounted } from 'vue'
import emitter from '@/utils/eventBus'

function handleMessage(data) {
  console.log('收到消息:', data)
}

onMounted(() => {
  emitter.on('message', handleMessage)
  // 支持通配符监听所有事件
  emitter.on('*', (type, event) => {
    console.log(`事件类型: ${type}`, event)
  })
})

onUnmounted(() => {
  // 组件卸载时取消监听，防止内存泄漏
  emitter.off('message', handleMessage)
})
</script>
```

### Pinia —— 全局状态管理

对于需要在多个组件间共享的状态，最佳实践是使用 Pinia 进行集中式状态管理。将在 2.6 节详细讲解。

### 常见面试题

**Q1: Vue 3 为什么移除全局事件总线？用什么替代？**

> Vue 3 移除了 `$on`、`$off` 和 `$once` 实例方法，因为全局事件总线容易导致事件来源不明、难以追踪、维护困难等问题，在大型项目中会造成"事件地狱"。Vue 3 推荐使用 `mitt` 库创建独立的事件总线实例，或使用 Pinia 进行状态管理。`mitt` 仅 200 字节，API 简单（`on`、`off`、`emit`），支持 TypeScript，是事件总线的最佳替代方案。

**Q2: provide/inject 是响应式的吗？如何保证后代不能随意修改提供的数据？**

> `provide/inject` 默认不是响应式的，如果直接传入一个普通对象，后代组件获取到的只是快照值。要使其响应式，需要传入 `ref` 或 `reactive` 对象。为了保证单向数据流，祖先组件应该使用 `readonly()` 包装提供的响应式数据，同时提供一个修改方法来让后代通过正规渠道更新状态。这样可以防止后代组件直接修改数据导致调试困难。

---

## 2.5 Vue Router（路由守卫、动态路由、懒加载、hash vs history 模式）

Vue Router 是 Vue 生态中官方的路由管理器，它与 Vue 核心深度集成，使构建单页应用（SPA）变得轻而易举。

### 路由守卫

路由守卫用于控制路由的导航行为，可以在导航前、导航后或导航过程中执行逻辑。分为三类：**全局守卫**、**路由独享守卫**、**组件内守卫**。

```javascript
// ===== 全局前置守卫 =====
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { 
      path: '/admin', 
      component: Admin,
      meta: { requiresAuth: true, roles: ['admin'] }
    },
    { path: '/login', component: Login }
  ]
})

// 全局前置守卫：每次导航前执行
router.beforeEach(async (to, from, next) => {
  // to: 即将进入的路由
  // from: 当前要离开的路由
  
  // 设置页面标题
  document.title = to.meta.title || '默认标题'
  
  // 权限校验
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('token')
    if (!token) {
      // 未登录，重定向到登录页
      return next({ path: '/login', query: { redirect: to.fullPath } })
    }
    
    // 角色校验
    if (to.meta.roles) {
      const userRole = await getUserRole()
      if (!to.meta.roles.includes(userRole)) {
        return next({ path: '/403' })
      }
    }
  }
  
  next()  // 放行
})

// 全局解析守卫（在所有组件内守卫和异步路由组件解析后执行）
router.beforeResolve((to, from) => {
  console.log('全局解析守卫')
})

// 全局后置钩子（导航完成后执行，没有 next）
router.afterEach((to, from) => {
  // 埋点、关闭加载动画等
  closeLoading()
})

// 全局错误处理
router.onError((error) => {
  console.error('路由错误:', error)
})
```

```javascript
// ===== 路由独享守卫 =====
const routes = [
  {
    path: '/user/:id',
    component: UserDetail,
    beforeEnter: (to, from, next) => {
      // 仅在此路由进入前执行
      const userId = parseInt(to.params.id)
      if (isNaN(userId)) {
        return next({ path: '/404' })
      }
      next()
    }
  }
]
```

```vue
<!-- 组件内守卫 -->
<script setup>
import { onBeforeRouteEnter, onBeforeRouteUpdate, onBeforeRouteLeave } from 'vue-router'

// 进入该组件前（不支持访问 this）
onBeforeRouteEnter((to, from, next) => {
  fetchData(to.params.id).then(data => {
    next(vm => vm.setData(data))
  })
})

// 当前组件路由更新时（参数变化但组件复用）
onBeforeRouteUpdate((to, from) => {
  // 例如从 /user/1 切换到 /user/2
  userId.value = to.params.id
  fetchUserData(to.params.id)
})

// 离开该组件前（常用于确认弹窗）
onBeforeRouteLeave((to, from, next) => {
  if (hasUnsavedChanges.value) {
    const answer = window.confirm('您有未保存的更改，确定要离开吗？')
    if (answer) next()
    else next(false)  // 取消导航
  } else {
    next()
  }
})
</script>
```

### 动态路由与懒加载

```javascript
const routes = [
  // 静态路由
  { path: '/', component: Home },
  
  // 懒加载：按需加载组件，减少首屏加载时间
  {
    path: '/about',
    component: () => import('@/views/About.vue')  // 返回 Promise
  },
  
  // 动态路由：参数匹配
  {
    path: '/user/:id',
    name: 'UserDetail',
    component: () => import('@/views/UserDetail.vue'),
    // 将路由参数映射为组件 props
    props: true,
    // 嵌套路由
    children: [
      { path: '', component: UserHome },
      { path: 'profile', component: UserProfile },
      { path: 'posts', component: UserPosts }
    ]
  },
  
  // 动态添加路由（权限控制场景）
  // 在获取用户权限后动态添加
]

// 动态添加路由
function addDynamicRoutes(permissions) {
  const asyncRoutes = generateRoutesFromPermissions(permissions)
  asyncRoutes.forEach(route => {
    router.addRoute(route)
  })
}

// 获取当前路由信息
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()   // 当前路由信息对象
const router = useRouter()  // 路由实例

// 常用属性和方法
console.log(route.path)        // 当前路径
console.log(route.params)      // 路由参数
console.log(route.query)       // 查询参数
console.log(route.meta)        // 路由元信息

router.push('/user/123')       // 导航到新路由
router.replace('/home')        // 替换当前路由
router.go(-1)                  // 后退
router.back()                  // 后退
```

### Hash vs History 模式

| 特性 | Hash 模式 | History 模式 |
|---|---|---|
| URL 示例 | `/#/user/123` | `/user/123` |
| 实现原理 | `onhashchange` 事件 | HTML5 History API (`pushState`/`replaceState`) |
| 浏览器支持 | 兼容 IE9+ | 兼容 IE10+ |
| 服务端要求 | 不需要特殊配置 | 需要配置 fallback 到 index.html |
| SEO | 不太友好 | 更友好 |
| 部署 | 简单 | 需要服务器配合 |

```javascript
// 生产环境部署 History 模式时的 Nginx 配置
// location / {
//   try_files $uri $uri/ /index.html;
// }
```

### 常见面试题

**Q1: 导航守卫的执行顺序是什么？**

> 完整的导航解析流程如下：1. 导航被触发；2. 在失活的组件里调用 `beforeRouteLeave`；3. 调用全局的 `beforeEach`；4. 在重用的组件里调用 `beforeRouteUpdate`；5. 在路由配置里调用 `beforeEnter`；6. 解析异步路由组件；7. 在被激活的组件里调用 `beforeRouteEnter`；8. 调用全局的 `beforeResolve`；9. 导航被确认；10. 调用全局的 `afterEach`；11. 触发 DOM 更新；12. 调用 `beforeRouteEnter` 守卫中传给 `next` 的回调函数。理解这个顺序对于排查路由导航问题非常重要。

**Q2: 如何基于权限动态生成路由？**

> 典型的实现方案是：1. 用户登录后获取其权限列表；2. 前端维护一个完整的路由表（包含每个路由所需的权限标识）；3. 根据用户权限过滤出有权限访问的路由；4. 使用 `router.addRoute()` 动态添加路由；5. 将过滤后的路由菜单渲染到侧边栏。需要注意的是，`addRoute` 添加的路由在刷新页面后会丢失，因此需要将用户权限信息持久化存储，并在应用初始化时重新加载。

---

## 2.6 Pinia 状态管理（Store、State、Getters、Actions、模块化）

Pinia 是 Vue 官方推荐的新一代状态管理库，作为 Vuex 的继任者，它拥有更简洁的 API、完整的 TypeScript 支持、更轻量的体积（仅 1KB），并且同时支持 Vue 2 和 Vue 3。

### Store 的核心概念

Pinia 的核心概念包括：**State**（状态）、**Getters**（计算属性）、**Actions**（操作方法）。与 Vuex 不同，Pinia 没有 `mutations`，状态修改直接在 `actions` 中进行，这大大简化了代码。

```javascript
// ===== stores/user.js =====
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 定义 Store：参数1为唯一ID，参数2为配置对象
export const useUserStore = defineStore('user', () => {
  // ===== State =====
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(null)
  const permissions = ref([])
  const loading = ref(false)
  
  // ===== Getters（计算属性）=====
  const isLoggedIn = computed(() => !!token.value)
  const userName = computed(() => userInfo.value?.name || '游客')
  const hasPermission = computed(() => {
    return (permission) => permissions.value.includes(permission)
  })
  
  // ===== Actions（方法）=====
  async function login(credentials) {
    loading.value = true
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        body: JSON.stringify(credentials)
      })
      const data = await res.json()
      token.value = data.token
      userInfo.value = data.userInfo
      permissions.value = data.permissions
      localStorage.setItem('token', data.token)
      return data
    } finally {
      loading.value = false
    }
  }
  
  function logout() {
    token.value = ''
    userInfo.value = null
    permissions.value = []
    localStorage.removeItem('token')
  }
  
  async function fetchUserInfo() {
    if (!token.value) return
    const res = await fetch('/api/user/info', {
      headers: { Authorization: `Bearer ${token.value}` }
    })
    userInfo.value = await res.json()
  }
  
  // 暴露所有状态和函数
  return {
    token, userInfo, permissions, loading,
    isLoggedIn, userName, hasPermission,
    login, logout, fetchUserInfo
  }
})
```

```vue
<!-- 组件中使用 Store -->
<template>
  <div class="user-panel">
    <p v-if="userStore.isLoggedIn">
      欢迎, {{ userStore.userName }}
    </p>
    <p v-else>请登录</p>
    
    <button v-if="!userStore.isLoggedIn" @click="handleLogin">登录</button>
    <button v-else @click="userStore.logout">退出</button>
    
    <p>加载状态: {{ userStore.loading ? '加载中...' : '就绪' }}</p>
  </div>
</template>

<script setup>
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

// 直接解构会失去响应式！需要使用 storeToRefs
import { storeToRefs } from 'pinia'
const { token, userInfo } = storeToRefs(userStore)

async function handleLogin() {
  await userStore.login({ username: 'admin', password: '123456' })
}

// 监听状态变化
import { watch } from 'vue'
watch(() => userStore.token, (newToken) => {
  console.log('Token 变化:', newToken ? '已登录' : '未登录')
})
</script>
```

### 模块化与最佳实践

```javascript
// ===== stores/index.js =====
import { createPinia } from 'pinia'

export default createPinia()

// ===== main.js =====
import { createApp } from 'vue'
import App from './App.vue'
import pinia from './stores'

const app = createApp(App)
app.use(pinia)
app.mount('#app')

// ===== 模块化 Store 示例 =====
// stores/cart.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useCartStore = defineStore('cart', () => {
  const items = ref([])
  
  const totalCount = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0))
  const totalPrice = computed(() => items.value.reduce((sum, item) => sum + item.price * item.quantity, 0))
  
  function addItem(product) {
    const existing = items.value.find(item => item.id === product.id)
    if (existing) {
      existing.quantity++
    } else {
      items.value.push({ ...product, quantity: 1 })
    }
  }
  
  function removeItem(productId) {
    const index = items.value.findIndex(item => item.id === productId)
    if (index > -1) items.value.splice(index, 1)
  }
  
  return { items, totalCount, totalPrice, addItem, removeItem }
})

// ===== 跨 Store 调用 =====
// stores/order.js
import { defineStore } from 'pinia'
import { useCartStore } from './cart'
import { useUserStore } from './user'

export const useOrderStore = defineStore('order', () => {
  async function createOrder() {
    const cart = useCartStore()
    const user = useUserStore()
    
    if (!user.isLoggedIn) {
      throw new Error('请先登录')
    }
    
    const res = await fetch('/api/orders', {
      method: 'POST',
      headers: { Authorization: `Bearer ${user.token}` },
      body: JSON.stringify({
        items: cart.items,
        totalAmount: cart.totalPrice
      })
    })
    
    // 下单成功后清空购物车
    cart.items = []
    return res.json()
  }
  
  return { createOrder }
})
```

### 常见面试题

**Q1: Pinia 相比 Vuex 有哪些优势？**

> 1. **更简洁的 API**：Pinia 取消了 Vuex 的 mutations，状态修改直接在 actions 中完成，减少了样板代码。2. **完整的 TypeScript 支持**：Pinia 从一开始就使用 TypeScript 编写，类型推断非常出色，无需额外标注。3. **更轻量**：核心代码仅约 1KB。4. **模块设计更合理**：每个 Store 都是独立的，不需要嵌套模块命名空间。5. **支持服务端渲染**：对 SSR 更友好。6. **开发工具支持**：Vue DevTools 原生支持，可以追踪状态变化。7. **同时支持 Vue 2 和 Vue 3**。

**Q2: 为什么直接解构 Pinia Store 会失去响应式？如何解决？**

> 因为 Pinia Store 中的状态本质上是 `ref` 和 `reactive` 对象，直接解构会丢失响应式连接（与 `reactive` 对象的解构问题相同）。解决方案是使用 `storeToRefs()` 工具函数，它会将 Store 中所有状态（state + getters）转换为 `ref`，同时保留 actions 为普通函数。例如：`const { count, doubleCount } = storeToRefs(store)` 保持响应式，而 `const { increment } = store` 可以直接解构 action。

---

## 2.7 虚拟 DOM 与 Diff 算法

虚拟 DOM（Virtual DOM）是 Vue 和 React 等现代前端框架的核心技术之一。它通过在内存中维护一个轻量级的 DOM 树表示，并在数据变化时计算出最小的 DOM 操作集，从而大幅提升渲染性能。

### 虚拟 DOM 的基本概念

虚拟 DOM 是一个普通的 JavaScript 对象，它描述了真实 DOM 的结构和属性。每次组件状态变化时，框架会先构建一个新的虚拟 DOM 树，然后与旧的虚拟 DOM 树进行比较（Diff），最后只将差异部分应用到真实 DOM 上。

```javascript
// 真实 DOM
// <div class="container">
//   <h1>Hello</h1>
//   <p>World</p>
// </div>

// 对应的虚拟 DOM 对象（简化版）
const vnode = {
  tag: 'div',
  props: { class: 'container' },
  children: [
    { tag: 'h1', props: {}, children: ['Hello'] },
    { tag: 'p', props: {}, children: ['World'] }
  ]
}

// Vue 3 的 VNode 结构更复杂，包含更多元信息
type VNode = {
  __v_isVNode: true,
  type: string | Component,  // 节点类型
  props: object | null,      // 属性
  children: VNode[] | string, // 子节点
  key: string | number,      // 唯一标识
  patchFlag: number,         // Vue3 优化标记
  shapeFlag: number,         // 节点类型标记
  // ... 其他内部属性
}
```

### Diff 算法的核心逻辑

Vue 的 Diff 算法采用**双端比较**策略，时间复杂度为 O(n)，而非传统的 O(n³) 树对比算法。其核心假设是：相同类型的组件产生类似的树形结构，相同类型的元素在列表中保持稳定的 key。

```javascript
// ===== Diff 算法核心逻辑（简化版） =====
function patchChildren(n1, n2, container) {
  const c1 = n1.children  // 旧子节点
  const c2 = n2.children  // 新子节点
  
  // 情况1：新子节点是文本
  if (typeof c2 === 'string') {
    if (typeof c1 === 'string') {
      if (c1 !== c2) container.textContent = c2
    } else {
      container.textContent = c2
    }
    return
  }
  
  // 情况2：新子节点是数组
  let i = 0
  const l2 = c2.length
  let e1 = c1.length - 1  // 旧子节点尾索引
  let e2 = l2 - 1          // 新子节点尾索引
  
  // 1. 从头部开始同步
  while (i <= e1 && i <= e2) {
    if (isSameVNodeType(c1[i], c2[i])) {
      patch(c1[i], c2[i], container)  // 递归 patch
    } else {
      break
    }
    i++
  }
  
  // 2. 从尾部开始同步
  while (i <= e1 && i <= e2) {
    if (isSameVNodeType(c1[e1], c2[e2])) {
      patch(c1[e1], c2[e2], container)
    } else {
      break
    }
    e1--
    e2--
  }
  
  // 3. 处理新增或删除
  if (i > e1) {
    // 新节点有剩余，说明是新增
    while (i <= e2) {
      patch(null, c2[i], container)
      i++
    }
  } else if (i > e2) {
    // 旧节点有剩余，说明是删除
    while (i <= e1) {
      unmount(c1[i])
      i++
    }
  } else {
    // 4. 中间对比：最复杂的情况
    // 使用 key 建立映射表，尽量减少 DOM 操作
    // ...（实际实现包含更复杂的优化）
  }
}

function isSameVNodeType(n1, n2) {
  // 判断两个 VNode 是否为同一类型（可复用）
  return n1.type === n2.type && n1.key === n2.key
}
```

### Vue 3 的优化策略

Vue 3 在编译阶段做了大量优化，使 Diff 过程更加高效：

1. **静态提升（Static Hoisting）**：将不依赖响应式数据的静态节点提升到渲染函数外部，避免每次更新时重新创建。
2. **Patch Flag**：在编译时标记动态节点（如 `:class`、`:id`、文本插值等），Diff 时只检查有标记的节点。
3. **Block Tree**：将模板中的动态节点收集到数组中，更新时只需遍历这个数组，跳过静态节点。

```javascript
// ===== 编译优化示例 =====
// 模板
// <div>
//   <h1>静态标题</h1>
//   <p>{{ dynamicMessage }}</p>
//   <span class="static">静态内容</span>
//   <span :class="dynamicClass">动态内容</span>
// </div>

// Vue 3 编译后的渲染函数（简化版）
function render(_ctx, _cache) {
  return _openBlock(), _createElementBlock("div", null, [
    // 静态节点被提升，只在初始化时创建一次
    _hoisted_1,  // <h1>静态标题</h1>
    // 动态节点带有 PatchFlag
    _createElementVNode("p", null, _toDisplayString(_ctx.dynamicMessage), 1 /* TEXT */),
    _hoisted_2,  // <span class="static">静态内容</span>
    _createElementVNode("span", {
      class: _normalizeClass(_ctx.dynamicClass)
    }, "动态内容", 2 /* CLASS */)
  ])
}
```

### 常见面试题

**Q1: 为什么 Vue 的 Diff 算法时间复杂度是 O(n) 而不是 O(n³)？**

> 传统的树对比算法（如 Levenshtein 距离）需要考虑所有可能的节点移动方式，时间复杂度确实是 O(n³)。但 Vue（和 React）采用的 Diff 算法做了两个关键假设来简化问题：1）不同类型的元素会产生完全不同的树（所以先比较类型，不同直接替换）；2）开发人员可以通过 key 属性暗示哪些子元素在渲染前后是稳定的。基于这两个假设，Diff 算法采用"分层对比 + 双端比较"的策略，只需按层级遍历一次，时间复杂度降为 O(n)。这种"贪心"策略虽然不一定找到最优解，但在实际 UI 场景中已经足够高效。

**Q2: 为什么在列表渲染中 key 属性很重要？不用 key 或 index 作为 key 有什么问题？**

> `key` 是 Vue 识别节点的唯一标识，它决定了 Diff 算法能否正确复用 DOM 节点。如果不设置 key，Vue 会采用"就地复用"策略，即尽量复用位置相同的 DOM 元素，这可能导致状态混乱（如输入框内容不随数据更新）。如果用 `index` 作为 key，当列表顺序变化时，index 不变但实际内容变了，Vue 会错误地认为节点没有变化，导致渲染问题。正确的做法是使用数据中唯一的、稳定的标识作为 key（如数据库主键 ID）。

---

## 2.8 自定义指令与插件开发

自定义指令和插件是 Vue 提供的高级扩展机制，允许开发者封装可复用的 DOM 操作逻辑和应用级功能。

### 自定义指令

Vue 3 的自定义指令与组件生命周期类似，提供了完整的钩子函数。自定义指令适合封装需要直接操作 DOM 的逻辑，如输入框聚焦、权限控制、懒加载等。

```javascript
// ===== 全局注册自定义指令 =====
// main.js
import { createApp } from 'vue'
import App from './App.vue'

const app = createApp(App)

// v-focus：自动聚焦指令
app.directive('focus', {
  // 指令挂载到 DOM 后执行
  mounted(el) {
    el.focus()
  }
})

// v-permission：权限控制指令
app.directive('permission', {
  mounted(el, binding) {
    const requiredPermission = binding.value
    const userPermissions = getUserPermissions() // 获取当前用户权限
    
    if (!userPermissions.includes(requiredPermission)) {
      // 无权限时移除元素
      el.remove()
      // 或者隐藏：el.style.display = 'none'
    }
  }
})

// v-debounce：防抖指令
app.directive('debounce', {
  mounted(el, binding) {
    const delay = binding.arg || 300  // v-debounce:500
    const handler = binding.value
    let timer = null
    
    el.addEventListener('click', () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        handler()
      }, delay)
    })
  },
  unmounted(el) {
    // 清理事件监听
    el.removeEventListener('click')
  }
})

// v-lazy：图片懒加载指令
app.directive('lazy', {
  mounted(el, binding) {
    const imgSrc = binding.value
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          el.src = imgSrc
          observer.unobserve(el)
        }
      })
    })
    observer.observe(el)
  }
})

app.mount('#app')
```

```vue
<!-- 组件中使用自定义指令 -->
<template>
  <div>
    <!-- 自动聚焦 -->
    <input v-focus placeholder="自动聚焦" />
    
    <!-- 权限控制 -->
    <button v-permission="'user:create'">创建用户</button>
    <button v-permission="'user:delete'">删除用户</button>
    
    <!-- 防抖点击 -->
    <button v-debounce:500="handleSubmit">提交（防抖500ms）</button>
    
    <!-- 图片懒加载 -->
    <img v-lazy="'/path/to/image.jpg'" alt="懒加载图片" />
  </div>
</template>
```

### 插件开发

Vue 插件是一个包含 `install` 方法的对象，或者一个直接接收 `app` 参数的函数。插件可以扩展 Vue 的全局功能，如添加全局属性、注册全局组件、添加全局指令、混入全局方法等。

```javascript
// ===== 创建一个 Vue 插件 =====
// plugins/toast.js
const ToastPlugin = {
  install(app, options = {}) {
    const defaultOptions = {
      duration: 3000,
      position: 'top-center',
      ...options
    }
    
    // 创建 Toast 组件实例
    function createToast(message, type = 'info') {
      const toastEl = document.createElement('div')
      toastEl.className = `toast toast-${type} toast-${defaultOptions.position}`
      toastEl.textContent = message
      document.body.appendChild(toastEl)
      
      // 自动移除
      setTimeout(() => {
        toastEl.classList.add('fade-out')
        setTimeout(() => toastEl.remove(), 300)
      }, defaultOptions.duration)
    }
    
    // 注册全局属性
    app.config.globalProperties.$toast = {
      info: (msg) => createToast(msg, 'info'),
      success: (msg) => createToast(msg, 'success'),
      error: (msg) => createToast(msg, 'error'),
      warning: (msg) => createToast(msg, 'warning')
    }
    
    // 同时提供 Composition API 方式
    app.provide('toast', app.config.globalProperties.$toast)
  }
}

export default ToastPlugin

// ===== 使用插件 =====
// main.js
import ToastPlugin from './plugins/toast'

app.use(ToastPlugin, { duration: 5000 })

// Options API 中使用
// this.$toast.success('操作成功！')

// Composition API 中使用
// const toast = inject('toast')
// toast.success('操作成功！')
```

### 常见面试题

**Q1: 自定义指令和组件有什么区别？什么时候用自定义指令？**

> 组件是对 UI 的封装，包含模板、样式和逻辑，输出的是一组 DOM 结构。自定义指令是对底层 DOM 操作的封装，它不涉及模板渲染，只负责操作已有的 DOM 元素。使用自定义指令的场景包括：1）需要直接操作 DOM 的通用逻辑（如自动聚焦、文本高亮）；2）与 DOM 事件强相关的功能（如点击外部关闭、拖拽）；3）性能敏感的 DOM 操作（如虚拟滚动）。但大多数情况应该优先考虑组件，因为组件的可维护性和可测试性更好。

**Q2: 如何开发一个支持 Vue 2 和 Vue 3 的通用插件？**

> 可以通过检测 Vue 版本来实现兼容。在插件的 `install` 方法中，Vue 2 会传入 `Vue` 构造函数，Vue 3 会传入 `app` 实例。通过判断参数类型来执行不同的逻辑：Vue 2 使用 `Vue.prototype` 扩展原型，Vue 3 使用 `app.config.globalProperties`。另外，Vue 2 和 Vue 3 的响应式 API 不同，需要分别使用 Vue 2 的 `Vue.observable` 或 Vue 3 的 `reactive`。许多流行的 UI 组件库（如 Element Plus、Vuetify）都采用了这种兼容策略。

---

## 2.9 性能优化（v-once、keep-alive、异步组件、虚拟列表）

性能优化是前端开发中永恒的话题，也是面试中的高频考点。Vue 提供了多种内置机制来帮助开发者优化应用性能。

### v-once

`v-once` 指令用于渲染一次性静态内容，后续数据变化不会触发重新渲染。适合用于不需要更新的纯展示内容，如文章详情、商品描述等。

```vue
<template>
  <div>
    <!-- 只渲染一次，后续 data 变化不更新 -->
    <article v-once>
      <h1>{{ article.title }}</h1>
      <div v-html="article.content"></div>
    </article>
    
    <!-- 这部分会正常响应式更新 -->
    <div class="comments">
      <p>评论数: {{ commentCount }}</p>
    </div>
  </div>
</template>
```

### keep-alive

`<keep-alive>` 是一个抽象组件，它可以缓存不活动的组件实例，而不是销毁它们。当组件在 `<keep-alive>` 内切换时，组件的状态（如表单输入、滚动位置）会被保留。

```vue
<template>
  <div class="tabs">
    <!-- Tab 切换按钮 -->
    <div class="tab-headers">
      <button 
        v-for="tab in tabs" 
        :key="tab.name"
        :class="{ active: currentTab === tab.name }"
        @click="currentTab = tab.name"
      >
        {{ tab.label }}
      </button>
    </div>
    
    <!-- 缓存 Tab 内容组件，避免重复创建和销毁 -->
    <KeepAlive :include="['UserProfile', 'UserSettings']" :exclude="['UserSecurity']" :max="10">
      <component :is="currentTabComponent" />
    </KeepAlive>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import UserProfile from './UserProfile.vue'
import UserSettings from './UserSettings.vue'
import UserSecurity from './UserSecurity.vue'

const currentTab = ref('UserProfile')
const tabs = [
  { name: 'UserProfile', label: '个人资料' },
  { name: 'UserSettings', label: '账号设置' },
  { name: 'UserSecurity', label: '安全设置' }
]

const currentTabComponent = computed(() => {
  const map = { UserProfile, UserSettings, UserSecurity }
  return map[currentTab.value]
})
</script>

<!-- 被 keep-alive 缓存的组件会有额外的生命周期钩子 -->
<script setup>
import { onActivated, onDeactivated } from 'vue'

// 组件被激活时（从缓存中恢复）
onActivated(() => {
  console.log('组件被激活')
  // 可以在此恢复定时器、WebSocket 连接等
})

// 组件被停用时（被缓存）
onDeactivated(() => {
  console.log('组件被缓存')
  // 可以在此暂停不需要的后台任务
})
</script>
```

### 异步组件与代码分割

异步组件允许将组件的加载延迟到需要渲染时，配合 Webpack/Vite 的代码分割功能，可以显著减少首屏加载的 JavaScript 体积。

```javascript
// ===== 异步组件的基本用法 =====
import { defineAsyncComponent } from 'vue'

// 方式1：简单用法
const AsyncModal = defineAsyncComponent(() => import('./Modal.vue'))

// 方式2：带加载状态和错误处理的完整配置
const AsyncChart = defineAsyncComponent({
  loader: () => import('./HeavyChart.vue'),
  loadingComponent: LoadingSpinner,    // 加载中显示的组件
  errorComponent: ErrorDisplay,        // 加载失败显示的组件
  delay: 200,                          // 延迟显示 loading（避免闪烁）
  timeout: 3000,                       // 超时时间
  suspensible: false                   // 是否配合 Suspense 使用
})

// ===== 路由懒加载（最常用场景）=====
const routes = [
  {
    path: '/dashboard',
    component: () => import(/* webpackChunkName: "dashboard" */ '@/views/Dashboard.vue')
  },
  {
    path: '/report',
    component: () => import(/* webpackChunkName: "report" */ '@/views/Report.vue')
  }
]
```

### 虚拟列表

当需要渲染大量数据列表（如聊天记录、日志列表）时，即使数据已经在内存中，渲染数千个 DOM 节点也会造成严重的性能问题。虚拟列表（Virtual List）只渲染可视区域内的元素，通过动态调整偏移量来模拟完整列表的滚动效果。

```vue
<template>
  <div class="virtual-list" ref="container" @scroll="handleScroll">
    <!-- 撑开滚动区域的总高度 -->
    <div class="phantom" :style="{ height: totalHeight + 'px' }"></div>
    
    <!-- 实际渲染的可见项 -->
    <div class="content" :style="{ transform: `translateY(${offsetY}px)` }">
      <div 
        v-for="item in visibleItems" 
        :key="item.id"
        class="list-item"
        :style="{ height: itemHeight + 'px' }"
      >
        {{ item.name }} - {{ item.description }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({
  items: { type: Array, required: true },
  itemHeight: { type: Number, default: 50 },
  buffer: { type: Number, default: 5 }  // 缓冲区大小
})

const container = ref(null)
const scrollTop = ref(0)
const containerHeight = ref(0)

// 总高度
const totalHeight = computed(() => props.items.length * props.itemHeight)

// 可见区域的起始索引
const startIndex = computed(() => {
  return Math.max(0, Math.floor(scrollTop.value / props.itemHeight) - props.buffer)
})

// 可见区域的结束索引
const endIndex = computed(() => {
  const visibleCount = Math.ceil(containerHeight.value / props.itemHeight)
  return Math.min(props.items.length, startIndex.value + visibleCount + props.buffer * 2)
})

// 实际渲染的项
const visibleItems = computed(() => {
  return props.items.slice(startIndex.value, endIndex.value)
})

// 偏移量
const offsetY = computed(() => startIndex.value * props.itemHeight)

function handleScroll() {
  scrollTop.value = container.value.scrollTop
}

onMounted(() => {
  containerHeight.value = container.value.clientHeight
})
</script>

<style scoped>
.virtual-list {
  position: relative;
  height: 400px;
  overflow-y: auto;
}
.phantom {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
}
.content {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
}
.list-item {
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid #eee;
}
</style>
```

### 常见面试题

**Q1: keep-alive 的缓存机制是什么？如何控制缓存？**

> `<keep-alive>` 内部维护了一个缓存对象（VNode 的映射表），当组件被切换出去时，不是调用 `unmount` 销毁，而是调用 `deactivate` 将其从 DOM 中移除但保留 VNode 实例。当组件再次激活时，调用 `activate` 将其重新挂载。控制缓存的方式有三种：1）`include` 属性（数组或正则），只有匹配的组件会被缓存；2）`exclude` 属性，匹配的组件不缓存；3）`max` 属性，限制最大缓存数量，采用 LRU（最近最少使用）策略淘汰。被缓存的组件会多出 `onActivated` 和 `onDeactivated` 两个生命周期钩子。

**Q2: 虚拟列表的原理是什么？如何处理不定高度的列表项？**

> 虚拟列表的核心原理是"只渲染可见区域 + 模拟滚动"。它用一个高度等于所有项总高度的"占位元素"（phantom）撑开滚动容器，然后通过监听滚动事件计算当前可见区域的起止索引，只渲染这部分数据。列表项通过 `transform: translateY` 定位到正确的位置。处理不定高度的情况更复杂，需要：1）先预设一个估计高度进行渲染；2）在项渲染完成后通过 `ResizeObserver` 或 `getBoundingClientRect` 获取真实高度；3）维护一个位置缓存表，记录每项的累计高度；4）滚动时根据缓存表计算正确的偏移量。vue-virtual-scroller 等成熟库已经实现了这些复杂逻辑。

---

## 2.10 Vite 构建工具（热更新原理、配置、插件）

Vite 是 Vue 团队开发的新一代前端构建工具，它在开发阶段使用原生 ES Modules 提供极速的冷启动和热更新（HMR），在生产构建阶段则使用 Rollup 进行打包。

### Vite 的核心优势

1. **极速冷启动**：无需打包，直接利用浏览器原生 ESM 支持，启动时间几乎与项目大小无关。
2. **即时的热更新**：基于 ESM 的 HMR，更新速度不受应用大小影响。
3. **优化的构建**：使用 Rollup 进行生产构建，支持代码分割、Tree Shaking 等优化。
4. **开箱即用的 TypeScript 支持**：原生支持 TS，无需额外配置 Babel。
5. **丰富的插件生态**：兼容 Rollup 插件，同时提供 Vite 专属 API。

### 热更新（HMR）原理

Vite 的 HMR 基于原生 ESM 实现。当文件修改时：

1. Vite 服务端通过 WebSocket 向客户端推送更新消息
2. 客户端接收到消息后，通过 `import()` 动态重新加载修改的模块
3. 更新后的模块通过 HMR API（`import.meta.hot`）通知其依赖方
4. 如果模块自身实现了 `accept` 回调，可以在不刷新页面的情况下局部更新

```javascript
// ===== HMR API 示例 =====
// stores/counter.js
import { ref } from 'vue'

export const count = ref(0)

// HMR：保留状态
if (import.meta.hot) {
  import.meta.hot.accept((newModule) => {
    console.log('模块热更新:', newModule)
  })
}

// ===== Vite 客户端 HMR 流程（简化）=====
// 1. 监听 WebSocket 消息
const socket = new WebSocket('ws://localhost:3000')

socket.addEventListener('message', async ({ data }) => {
  const payload = JSON.parse(data)
  
  switch (payload.type) {
    case 'update':
      // 更新模块
      for (const update of payload.updates) {
        if (update.type === 'js-update') {
          await fetchUpdate(update)
        } else if (update.type === 'css-update') {
          updateStyle(update.path)
        }
      }
      break
    case 'full-reload':
      // 无法 HMR，整页刷新
      location.reload()
      break
  }
})

async function fetchUpdate(update) {
  const newModule = await import(update.path + '?t=' + Date.now())
  // 执行模块的 accept 回调
  const hotContext = hotModulesMap.get(update.path)
  if (hotContext?.callbacks) {
    hotContext.callbacks.forEach(cb => cb(newModule))
  }
}
```

### Vite 配置详解

```javascript
// ===== vite.config.js =====
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ command, mode }) => {
  // command: 'serve' | 'build'
  // mode: 'development' | 'production' | 自定义
  
  return {
    // ===== 基础配置 =====
    root: process.cwd(),        // 项目根目录
    base: '/',                  // 公共基础路径
    publicDir: 'public',        // 静态资源目录
    
    // ===== 路径别名 =====
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        '@components': resolve(__dirname, 'src/components'),
        '@stores': resolve(__dirname, 'src/stores'),
        '@api': resolve(__dirname, 'src/api')
      }
    },
    
    // ===== 插件 =====
    plugins: [
      vue(),
      // 其他插件...
    ],
    
    // ===== CSS 配置 =====
    css: {
      preprocessorOptions: {
        scss: {
          additionalData: `@use "@/styles/variables.scss" as *;`
        }
      },
      modules: {
        localsConvention: 'camelCaseOnly'
      }
    },
    
    // ===== 开发服务器 =====
    server: {
      port: 3000,
      open: true,              // 自动打开浏览器
      cors: true,              // 启用 CORS
      proxy: {                 // 代理配置
        '/api': {
          target: 'http://localhost:8080',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, '')
        }
      },
      hmr: {
        overlay: true  // 编译错误显示在浏览器中
      }
    },
    
    // ===== 构建配置 =====
    build: {
      target: 'esnext',        // 构建目标
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: mode !== 'production',
      minify: 'terser',        // 压缩工具
      rollupOptions: {
        output: {
          // 代码分割策略
          manualChunks: {
            vue: ['vue', 'vue-router', 'pinia'],
            ui: ['element-plus']
          }
        }
      },
      // 资源内联阈值（小于此值的资源会内联为 base64）
      assetsInlineLimit: 4096
    },
    
    // ===== 依赖优化 =====
    optimizeDeps: {
      include: ['lodash-es', 'axios'],  // 预构建的依赖
      exclude: []  // 不预构建的依赖
    },
    
    // ===== 环境变量 =====
    envPrefix: 'VITE_'  // 暴露给客户端的环境变量前缀
  }
})
```

### 插件开发

```javascript
// ===== 自定义 Vite 插件示例 =====
// plugins/my-plugin.js
export default function myPlugin(options = {}) {
  return {
    name: 'vite-plugin-my-plugin',
    
    // 配置加载前执行
    config(config, { command }) {
      if (command === 'build') {
        // 修改构建配置
        config.build.rollupOptions = {
          ...config.build.rollupOptions,
          // 自定义配置
        }
      }
    },
    
    // 解析 import 时触发
    resolveId(source) {
      if (source === 'virtual:my-module') {
        return source  // 标记为虚拟模块
      }
    },
    
    // 加载模块内容
    load(id) {
      if (id === 'virtual:my-module') {
        return `export const message = "Hello from virtual module!"`
      }
    },
    
    // 转换代码
    transform(code, id) {
      if (id.endsWith('.vue')) {
        // 对 Vue 文件进行额外处理
        return code
      }
    },
    
    // 构建完成后执行
    closeBundle() {
      console.log('构建完成！')
    }
  }
}
```

### 常见面试题

**Q1: Vite 和 Webpack 的主要区别是什么？为什么 Vite 启动更快？**

> 核心区别在于开发阶段的构建方式。Webpack 在启动时需要先构建完整的依赖图，将所有模块打包成 bundle，这个过程随着项目规模增大而显著变慢。Vite 在开发阶段利用浏览器原生 ESM 支持，不预先打包，而是让浏览器直接请求源文件。当浏览器请求某个模块时，Vite 服务端按需编译（如将 Vue 文件编译为 JS），返回给浏览器。由于现代浏览器原生支持 ESM，且 Vite 使用 esbuild（Go 编写）进行预构建，比 JavaScript 编写的 Webpack 快 10-100 倍。生产构建时，Vite 使用 Rollup 打包，与 Webpack 类似。

**Q2: Vite 如何处理 CommonJS 依赖？**

> Vite 基于 ESM 工作，但许多 npm 包使用 CommonJS 格式。Vite 在首次启动时会执行"依赖预构建"：使用 esbuild 将 CJS 依赖转换为 ESM 格式，并将多个分散的小文件合并为单个文件，以减少 HTTP 请求数量。预构建的结果缓存在 `node_modules/.vite` 目录中。可以通过 `optimizeDeps.include` 配置手动指定需要预构建的依赖，`optimizeDeps.exclude` 排除不需要预构建的依赖。如果安装了新的 CJS 依赖，需要重启开发服务器或删除缓存重新预构建。

---

## 2.11 与后端交互（Axios 封装、拦截器、JWT 认证流程）

前端与后端的交互是 Web 应用的核心环节。良好的 HTTP 请求封装可以大幅提升开发效率和代码可维护性。

### Axios 封装

```javascript
// ===== utils/request.js =====
import axios from 'axios'
import { useUserStore } from '@/stores/user'
import router from '@/router'

// 创建 axios 实例
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// ===== 请求拦截器 =====
request.interceptors.request.use(
  (config) => {
    // 在发送请求之前做些什么
    const userStore = useUserStore()
    
    // 添加认证头
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    
    // 添加请求时间戳（防止缓存）
    if (config.method === 'get') {
      config.params = { ...config.params, _t: Date.now() }
    }
    
    // 显示 loading
    // showLoading()
    
    return config
  },
  (error) => {
    // 对请求错误做些什么
    return Promise.reject(error)
  }
)

// ===== 响应拦截器 =====
request.interceptors.response.use(
  (response) => {
    // 对响应数据做点什么
    // hideLoading()
    
    const res = response.data
    
    // 根据后端约定的状态码处理
    if (res.code !== 200) {
      // 业务错误
      showErrorMessage(res.message || '请求失败')
      
      // 特定错误码处理
      if (res.code === 401) {
        // 未授权，跳转到登录页
        const userStore = useUserStore()
        userStore.logout()
        router.push('/login')
      }
      
      return Promise.reject(new Error(res.message))
    }
    
    return res.data  // 只返回数据部分
  },
  (error) => {
    // 对响应错误做点什么
    // hideLoading()
    
    if (error.response) {
      // 服务器返回了错误状态码
      const status = error.response.status
      const messageMap = {
        400: '请求参数错误',
        401: '未授权，请重新登录',
        403: '拒绝访问',
        404: '请求的资源不存在',
        500: '服务器内部错误',
        502: '网关错误',
        503: '服务不可用'
      }
      showErrorMessage(messageMap[status] || `请求失败: ${status}`)
      
      if (status === 401) {
        const userStore = useUserStore()
        userStore.logout()
        router.push('/login')
      }
    } else if (error.request) {
      // 请求已发出但没有收到响应
      showErrorMessage('网络连接失败，请检查网络')
    } else {
      showErrorMessage('请求配置错误')
    }
    
    return Promise.reject(error)
  }
)

export default request
```

### API 模块化管理

```javascript
// ===== api/user.js =====
import request from '@/utils/request'

export const userApi = {
  // 登录
  login(data) {
    return request.post('/auth/login', data)
  },
  
  // 注册
  register(data) {
    return request.post('/auth/register', data)
  },
  
  // 获取用户信息
  getUserInfo() {
    return request.get('/user/info')
  },
  
  // 更新用户信息
  updateUserInfo(data) {
    return request.put('/user/info', data)
  },
  
  // 上传头像
  uploadAvatar(file) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/user/avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  }
}

// ===== 组件中使用 =====
<script setup>
import { userApi } from '@/api/user'

async function handleLogin() {
  try {
    const data = await userApi.login({
      username: form.username,
      password: form.password
    })
    // 处理登录成功
  } catch (error) {
    // 错误已被拦截器统一处理
    console.error('登录失败:', error)
  }
}
</script>
```

### JWT 认证流程

JWT（JSON Web Token）是目前最流行的无状态认证方案。典型的认证流程如下：

```
+--------+                                           +--------+
| 客户端  |                                           | 服务端  |
+--------+                                           +--------+
    |                                                    |
    |  1. POST /auth/login {username, password}         |
    | -------------------------------------------------> |
    |                                                    |
    |                    2. 验证成功                     |
    |              返回 {accessToken, refreshToken}       |
    | <------------------------------------------------- |
    |                                                    |
    |  3. 存储 token（localStorage / httpOnly Cookie）    |
    |                                                    |
    |  4. 后续请求携带 Authorization: Bearer <token>     |
    | -------------------------------------------------> |
    |                                                    |
    |                    5. 验证 token 有效期             |
    |              过期则返回 401                        |
    | <------------------------------------------------- |
    |                                                    |
    |  6. 使用 refreshToken 请求新 accessToken           |
    |      POST /auth/refresh {refreshToken}             |
    | -------------------------------------------------> |
    |                                                    |
    |              7. 返回新的 accessToken                |
    | <------------------------------------------------- |
```

```javascript
// ===== Token 刷新机制 =====
import axios from 'axios'

let isRefreshing = false
let refreshSubscribers = []

// 订阅 token 刷新
function subscribeTokenRefresh(callback) {
  refreshSubscribers.push(callback)
}

// 通知所有订阅者
function onTokenRefreshed(newToken) {
  refreshSubscribers.forEach(callback => callback(newToken))
  refreshSubscribers = []
}

// 响应拦截器中处理 401
request.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    
    // 如果是 401 且不是刷新 token 的请求
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // 等待 token 刷新完成
        return new Promise(resolve => {
          subscribeTokenRefresh(newToken => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            resolve(request(originalRequest))
          })
        })
      }
      
      originalRequest._retry = true
      isRefreshing = true
      
      try {
        const refreshToken = localStorage.getItem('refreshToken')
        const res = await axios.post('/auth/refresh', { refreshToken })
        const newAccessToken = res.data.accessToken
        
        localStorage.setItem('token', newAccessToken)
        onTokenRefreshed(newAccessToken)
        
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
        return request(originalRequest)
      } catch (refreshError) {
        // 刷新失败，跳转登录
        localStorage.removeItem('token')
        localStorage.removeItem('refreshToken')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }
    
    return Promise.reject(error)
  }
)
```

### 常见面试题

**Q1: 为什么要对 Axios 进行二次封装？而不是直接使用 axios.get/axios.post？**

> 直接调用 `axios.get` 会导致以下问题：1）基础配置（baseURL、timeout）需要在每个请求中重复设置；2）认证头（Authorization）需要手动添加；3）错误处理逻辑分散在各处，难以统一维护；4）Loading 状态控制需要每个请求单独处理；5）请求/响应数据的转换逻辑重复。通过二次封装，可以集中处理这些横切关注点：统一配置、自动添加 Token、统一错误处理和提示、自动 Loading 控制、响应数据解构、请求取消等。封装后的 API 模块更加语义化，也更便于维护和测试。

**Q2: JWT 的 accessToken 和 refreshToken 的设计目的是什么？如何安全地存储 token？**

> `accessToken` 有效期短（通常 15 分钟），用于日常 API 请求的认证；`refreshToken` 有效期长（通常 7-30 天），专门用于在 `accessToken` 过期后获取新的 `accessToken`。这种双 Token 机制兼顾了安全性和用户体验：短有效期的 accessToken 降低了被盗后的风险窗口，而 refreshToken 机制避免了用户频繁重新登录。存储方案：1）**localStorage**：简单易用，但存在 XSS 攻击风险（恶意脚本可读取）；2）**httpOnly Cookie**：通过 `Set-Cookie: token=xxx; HttpOnly; Secure; SameSite=Strict` 设置，JS 无法读取，防 XSS 但需处理 CSRF；3）**内存存储**（最安全的做法）：将 token 保存在内存中（如 Pinia Store），页面刷新后通过 refreshToken 重新获取。生产环境推荐 Cookie + CSRF Token 方案，或配合后端 SameSite 策略。

---

## 2.12 TypeScript 在 Vue3 中的应用

TypeScript 为 Vue 3 带来了强大的类型安全保障。Vue 3 从底层就使用 TypeScript 重写，对 TS 的支持远超 Vue 2。

### 组合式函数的类型定义

```typescript
// ===== composables/useAsync.ts =====
import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'

// 定义异步状态的接口
interface AsyncState<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<Error | null>
  execute: (...args: any[]) => Promise<void>
}

// 泛型组合式函数
export function useAsync<T>(
  asyncFn: (...args: any[]) => Promise<T>
): AsyncState<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<Error | null>(null)

  async function execute(...args: any[]) {
    loading.value = true
    error.value = null
    try {
      data.value = await asyncFn(...args)
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, execute }
}

// 使用
const { data: users, loading, error, execute: fetchUsers } = useAsync<User[]>(
  () => fetch('/api/users').then(r => r.json())
)
```

### Props 和 Emits 的类型定义

```vue
<!-- ===== 带类型的组件示例 ===== -->
<template>
  <div class="user-card" :class="{ active: isActive }">
    <img :src="avatar" :alt="name" />
    <h3>{{ name }}</h3>
    <p>{{ email }}</p>
    <button @click="handleClick">查看详情</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// 定义 Props 接口
interface UserCardProps {
  id: number
  name: string
  email: string
  avatar?: string  // 可选属性
  status?: 'active' | 'inactive' | 'pending'  // 联合类型
}

// 定义 Emits 类型
interface UserCardEmits {
  (e: 'click', id: number): void
  (e: 'update:status', status: UserCardProps['status']): void
}

// 带默认值的 Props
const props = withDefaults(defineProps<UserCardProps>(), {
  avatar: '/default-avatar.png',
  status: 'active'
})

const emit = defineEmits<UserCardEmits>()

const isActive = computed(() => props.status === 'active')

function handleClick() {
  emit('click', props.id)
}
</script>
```

### Pinia Store 的类型定义

```typescript
// ===== stores/user.ts =====
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'

// 定义数据接口
export interface User {
  id: number
  name: string
  email: string
  role: 'admin' | 'user' | 'guest'
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthResponse {
  token: string
  user: User
}

// 类型安全的 Store
export const useUserStore = defineStore('user', () => {
  // State
  const token: Ref<string> = ref('')
  const userInfo: Ref<User | null> = ref(null)
  
  // Getters
  const isLoggedIn: ComputedRef<boolean> = computed(() => !!token.value)
  const isAdmin: ComputedRef<boolean> = computed(() => userInfo.value?.role === 'admin')
  
  // Actions
  async function login(credentials: LoginCredentials): Promise<AuthResponse> {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials)
    })
    
    if (!response.ok) {
      throw new Error('登录失败')
    }
    
    const data: AuthResponse = await response.json()
    token.value = data.token
    userInfo.value = data.user
    
    return data
  }
  
  function logout(): void {
    token.value = ''
    userInfo.value = null
  }
  
  return {
    token,
    userInfo,
    isLoggedIn,
    isAdmin,
    login,
    logout
  }
})
```

### Vue Router 的类型扩展

```typescript
// ===== types/router.d.ts =====
import 'vue-router'

// 扩展路由元信息类型
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    requiresAuth?: boolean
    roles?: string[]
    keepAlive?: boolean
    icon?: string
  }
}

// ===== router/index.ts =====
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首页', keepAlive: true }
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/Admin.vue'),
    meta: { 
      title: '管理后台', 
      requiresAuth: true, 
      roles: ['admin'] 
    }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
```

### Vite + TypeScript 配置

```json
// ===== tsconfig.json =====
{
  "compilerOptions": {
    "target": "ESNext",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ESNext", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@components/*": ["src/components/*"],
      "@stores/*": ["src/stores/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### 常见面试题

**Q1: Vue 3 的 defineProps 和 defineEmits 宏函数支持 TypeScript 的类型定义吗？**

> Vue 3.2+ 引入的 `<script setup>` 语法对 TypeScript 有 excellent 的支持。`defineProps` 和 `defineEmits` 可以接受泛型参数来定义类型：
> - `defineProps<PropsInterface>()` 可以自动推断 prop 类型、是否可选、默认值等
> - `withDefaults(defineProps<Props>(), { default: 'value' })` 用于设置带类型的默认值
> - `defineEmits<EmitsType>()` 可以严格限定 emit 事件的名称和参数类型
> 这些宏函数在编译阶段被转换为运行时选项，因此不需要导入。TypeScript 可以在编译时检查 prop 类型和 emit 事件，提供完整的 IDE 智能提示和类型检查。

**Q2: 在 Vue 3 + TypeScript 项目中，如何解决第三方库没有类型定义的问题？**

> 解决方案有几种：1）安装对应的 `@types/xxx` 类型包（如果有社区维护的话）；2）在项目根目录创建 `shims-xxx.d.ts` 声明文件，为库提供类型声明：`declare module 'xxx' { const content: any; export default content; }`；3）使用 `// @ts-ignore` 或 `// @ts-expect-error` 临时跳过类型检查（不推荐长期使用）；4）自己编写详细的 `.d.ts` 类型声明文件；5）如果库是用 JS 编写的，可以考虑使用 JSDoc 注释或提交 PR 为其添加类型支持。对于 Vite 项目，还需要在 `tsconfig.json` 的 `include` 中确保包含了这些声明文件。

---

> **本章小结**：Vue 前端技术栈涵盖响应式系统、组件通信、路由管理、状态管理、性能优化和工程化等多个维度。掌握这些核心概念和最佳实践，不仅能在面试中从容应对，更能指导日常开发写出高质量、可维护的 Vue 应用。建议读者结合官方文档和实际项目进行深入实践，将知识内化为自己的能力。




---


# 第 3 章：FastAPI 框架

> 本章深入讲解 FastAPI 框架的核心机制、设计哲学与工程实践，帮助读者在面试中从容应对各类 FastAPI 相关问题。

---

## 1. FastAPI 核心特性（异步、类型注解、自动文档）

FastAPI 是由 Sebastián Ramírez（@tiangolo）开发的高性能 Python Web 框架，它基于 Starlette（ASGI 工具集）和 Pydantic（数据验证）构建，自 2018 年发布以来迅速成为 Python 后端开发的主流选择之一。其设计哲学深受现代 TypeScript/Node.js 生态影响，将 Python 3.6+ 引入的类型注解系统（PEP 484）提升到了框架核心层面。

**异步支持**是 FastAPI 的首要特性。它原生基于 `async`/`await` 语法，允许开发者编写非阻塞的 I/O 密集型代码。在处理高并发场景（如大量数据库查询、外部 API 调用）时，异步模型可以显著减少线程/进程开销。FastAPI 内部使用 Starlette 的 ASGI 接口，这意味着它可以与 Uvicorn、Hypercorn 等异步服务器无缝协作，轻松支撑数千并发连接。

**类型注解驱动**是 FastAPI 区别于 Flask/Django 的核心差异。开发者只需在函数参数和返回值上使用 Python 标准类型提示，FastAPI 就能自动完成：请求参数解析与校验、JSON Schema 生成、数据序列化与反序列化。这一设计大幅减少了样板代码（Boilerplate），让接口定义即文档。

**自动文档生成**是 FastAPI 的招牌功能。框架内置集成了 Swagger UI（`/docs`）和 ReDoc（`/redoc`），只要定义了路由和模型，交互式 API 文档就会自动生成。这不仅省去了手动维护文档的麻烦，更重要的是保证了文档与代码的实时同步——代码即文档（Docs as Code）的实践典范。

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="用户服务", version="1.0.0")

class User(BaseModel):
    """用户数据模型"""
    id: int
    name: str
    email: str
    is_active: bool = True  # 默认值

@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    """
    根据用户ID获取用户信息
    - 路径参数 user_id 会被自动校验为 int 类型
    - 返回值会被自动序列化为 User 模型对应的 JSON
    """
    return User(id=user_id, name="张三", email="zhangsan@example.com")

@app.post("/users", response_model=User, status_code=201)
async def create_user(user: User):
    """
    创建新用户
    - 请求体会被自动解析并校验为 User 模型
    - 如果字段类型不匹配，FastAPI 会返回 422 自动校验错误
    """
    # 实际业务中这里会写入数据库
    return user

# 启动命令：uvicorn main:app --reload
# 访问 http://127.0.0.1:8000/docs 查看自动生成的 Swagger UI 文档
```

### 常见面试题

**Q1：FastAPI 与 Flask/Django 相比，核心优势是什么？**

> 从三个维度回答：① **性能**：FastAPI 基于 ASGI 和异步 IO，在同等硬件条件下并发处理能力远超 Flask（WSGI）和 Django（同步为主）；② **开发效率**：类型注解自动驱动数据校验和文档生成，减少 40% 以上的样板代码；③ **工程规范**：内置数据校验、依赖注入、OAuth2 等现代 Web 开发必需特性，而 Flask 需要借助扩展，Django 则较为笨重。

**Q2：FastAPI 的自动文档是如何实现的？**

> FastAPI 在启动时会遍历所有注册的路由，提取函数签名中的类型注解、Pydantic 模型的字段定义、路径参数/查询参数的配置等信息，自动生成符合 OpenAPI 规范的 JSON 描述文件（`/openapi.json`）。Swagger UI 和 ReDoc 本质上是读取这个 JSON 并渲染为可视化界面的前端组件。由于文档完全从代码推导而来，只要代码更新，文档就实时同步。

---

## 2. 路由与请求处理（Path/Query/Body/Header/Cookie/Form/File）

FastAPI 的请求参数解析机制是其最核心的设计亮点之一。它通过智能解析函数参数的类型注解和默认值，自动区分参数来源：路径参数（Path）、查询参数（Query）、请求体（Body）、请求头（Header）、Cookie 以及表单/文件上传（Form/File）。这种"声明式"的设计让开发者无需手动解析 `request` 对象。

**路径参数（Path Parameters）**：通过 URL 路径段传递，使用 `{}` 语法声明。FastAPI 会自动将路径值转换为声明的类型，若转换失败则返回 422 错误。支持路径转换器（如 `{user_id:int}`）和正则校验。

**查询参数（Query Parameters）**：通过 URL 查询字符串（`?key=value`）传递。默认情况下，非路径类型的基本类型参数会被识别为查询参数。支持必填/可选、默认值、别名、弃用标记等配置。

**请求体（Body）**：当参数类型为 Pydantic 模型时，FastAPI 自动从请求体中解析 JSON 数据并反序列化。支持嵌套模型、列表模型等复杂结构。

**请求头与 Cookie**：使用 `Header` 和 `Cookie` 依赖显式声明。Header 参数名会自动从 Python 的蛇形命名转换为 HTTP 的短横线命名（如 `user_agent` → `User-Agent`）。

**表单与文件**：`Form` 用于接收 `application/x-www-form-urlencoded` 数据，`File`/`UploadFile` 用于处理文件上传。`UploadFile` 是 FastAPI 的增强类型，提供异步读取、`seek()`、`file` 对象访问等能力，避免一次性将大文件载入内存。

```python
from fastapi import FastAPI, Path, Query, Header, Cookie, Form, File, UploadFile
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()

class Item(BaseModel):
    """商品模型"""
    name: str
    price: float
    tags: List[str] = []

# 路径参数 + 查询参数组合
@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(..., title="商品ID", ge=1, description="必须大于0"),
    q: Optional[str] = Query(None, min_length=3, max_length=50, description="搜索关键词"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    """
    获取商品列表
    - item_id: 路径参数，必填，必须 >= 1
    - q: 查询参数，可选，长度 3-50
    - skip/limit: 分页参数，带范围限制
    """
    return {"item_id": item_id, "q": q, "skip": skip, "limit": limit}

# 请求体（JSON）
@app.post("/items")
async def create_item(item: Item):
    """创建商品，请求体必须是合法的 Item JSON"""
    return {"item": item, "total": item.price * 1.08}  # 含税费计算

# 请求头与 Cookie
@app.get("/users/me")
async def read_current_user(
    user_agent: Optional[str] = Header(None, description="浏览器UA"),
    session_id: Optional[str] = Cookie(None, description="会话ID")
):
    """获取当前登录用户信息"""
    return {"user_agent": user_agent, "session_id": session_id}

# 表单提交 + 文件上传
@app.post("/upload")
async def upload_file(
    description: str = Form(..., description="文件描述"),
    file: UploadFile = File(..., description="上传的文件")
):
    """
    文件上传接口
    - UploadFile 支持异步读取，避免大文件内存溢出
    - 可通过 file.content_type 获取 MIME 类型
    """
    content = await file.read()  # 异步读取文件内容
    return {
        "filename": file.filename,
        "size": len(content),
        "content_type": file.content_type,
        "description": description
    }

# 同时接收文件和 JSON 数据（multipart 混合）
@app.post("/items-with-image")
async def create_item_with_image(
    item: str = Form(..., description="JSON字符串形式的Item数据"),
    image: UploadFile = File(...)
):
    """创建商品并上传封面图"""
    import json
    item_data = json.loads(item)
    return {"item": item_data, "image": image.filename}
```

### 常见面试题

**Q1：FastAPI 是如何区分 Path、Query、Body 参数的？**

> FastAPI 按照以下优先级判断参数来源：① 如果参数名出现在路由路径的 `{}` 中，则为 **Path 参数**；② 如果参数类型是 Pydantic 模型（`BaseModel` 子类），则为 **Body 参数**；③ 如果参数是基本类型（`int`、`str`、`bool` 等）或可选基本类型，且未在路径中声明，则为 **Query 参数**；④ 使用显式的 `Path()`、`Query()`、`Body()`、`Header()`、`Cookie()`、`Form()`、`File()` 可以覆盖默认推断。这一机制完全基于类型注解和默认值进行静态分析。

**Q2：`File` 和 `UploadFile` 有什么区别？大文件上传应该怎么做？**

> `File` 接收的是 `bytes` 类型，会将整个文件内容读入内存，适合小文件；`UploadFile` 是 FastAPI 封装的增强类型，底层使用 `python-multipart` 的 `SpooledTemporaryFile`，小文件存内存、大文件自动转存磁盘临时文件。`UploadFile` 提供 `read()`、`seek()`、`write()`、`file`（底层文件对象）等 API，支持流式处理。大文件上传应始终使用 `UploadFile`，并考虑配合 `BackgroundTasks` 异步处理或直传对象存储（OSS/S3）。

---

## 3. Pydantic 模型与数据校验

Pydantic 是 FastAPI 的数据验证和序列化引擎，它利用 Python 类型注解实现运行时数据校验。在 FastAPI 中，Pydantic 模型不仅是请求/响应的数据结构定义，更是接口契约（Contract）的代码化表达。

Pydantic v2（2023 年发布）进行了全面重构，基于 Rust 编写的 `pydantic-core` 将校验性能提升了 5-50 倍。FastAPI 0.100+ 版本已全面适配 Pydantic v2。v2 中 `BaseModel` 的核心方法有所调整：`model_validate()` 替代 `parse_obj()`，`model_dump()` 替代 `dict()`，`model_dump_json()` 替代 `json()`。

**字段类型与约束**：Pydantic 支持所有 Python 标准类型（`int`、`str`、`float`、`bool`、`list`、`dict`、`datetime` 等），以及 `typing` 模块的泛型（`Optional`、`List`、`Dict`、`Union` 等）。通过 `Field()` 函数可以为字段附加约束：`gt`/`ge`（大于/大于等于）、`lt`/`le`（小于/小于等于）、`min_length`/`max_length`（字符串长度）、`regex`（正则匹配）、`default`（默认值）、`description`（文档描述）等。

**嵌套模型**：Pydantic 支持模型嵌套，这在处理复杂业务对象时非常实用。例如一个订单包含多个商品，每个商品有 SKU 和库存信息。

**自定义校验器**：通过 `@field_validator` 和 `@model_validator` 装饰器，可以添加业务级校验逻辑。`@field_validator` 校验单个字段，`@model_validator` 校验整个模型（如密码与确认密码是否一致）。

**Config 配置**：通过嵌套的 `Config` 类或 `model_config` 字典，可以控制模型的行为，如 `extra='forbid'`（禁止额外字段）、`str_to_lower=True`（自动转小写）、`validate_assignment=True`（赋值时触发校验）等。

```python
from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr
from typing import List, Optional
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    """订单状态枚举"""
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"

class Address(BaseModel):
    """地址模型"""
    province: str = Field(..., min_length=2, max_length=20, description="省份")
    city: str = Field(..., min_length=2, max_length=20, description="城市")
    detail: str = Field(..., min_length=5, max_length=200, description="详细地址")
    zipcode: Optional[str] = Field(None, pattern=r'^\d{6}$', description="邮编")

class OrderItem(BaseModel):
    """订单商品项"""
    sku: str = Field(..., min_length=8, max_length=20, description="SKU编码")
    name: str = Field(..., description="商品名称")
    quantity: int = Field(..., gt=0, le=999, description="购买数量")
    unit_price: float = Field(..., gt=0, description="单价")

    @field_validator('sku')
    @classmethod
    def sku_must_be_uppercase(cls, v: str) -> str:
        """自定义校验器：SKU 必须为大写"""
        if not v.isupper():
            raise ValueError('SKU 必须为大写字母和数字')
        return v

class OrderCreate(BaseModel):
    """创建订单请求模型"""
    user_id: int = Field(..., gt=0, description="用户ID")
    items: List[OrderItem] = Field(..., min_length=1, description="商品列表")
    address: Address = Field(..., description="收货地址")
    coupon_code: Optional[str] = Field(None, max_length=20, description="优惠券码")
    remark: Optional[str] = Field(None, max_length=500, description="订单备注")

    @model_validator(mode='after')
    def check_order_total(self):
        """模型级校验器：订单总金额必须大于 0"""
        total = sum(item.quantity * item.unit_price for item in self.items)
        if total <= 0:
            raise ValueError('订单总金额必须大于0')
        return self

class OrderResponse(BaseModel):
    """订单响应模型"""
    order_id: str = Field(..., description="订单编号")
    status: OrderStatus = Field(default=OrderStatus.PENDING, description="订单状态")
    total_amount: float = Field(..., description="订单总金额")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    items: List[OrderItem] = Field(..., description="商品列表")

    model_config = {
        "json_schema_extra": {
            "example": {
                "order_id": "ORD202401010001",
                "status": "pending",
                "total_amount": 299.50,
                "items": [
                    {"sku": "SKU123456", "name": "Python编程", "quantity": 1, "unit_price": 299.50}
                ]
            }
        }
    }

# FastAPI 路由中使用
from fastapi import FastAPI

app = FastAPI()

@app.post("/orders", response_model=OrderResponse)
async def create_order(order: OrderCreate):
    """创建订单接口"""
    total = sum(item.quantity * item.unit_price for item in order.items)
    return OrderResponse(
        order_id=f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}",
        total_amount=total,
        items=order.items
    )
```

### 常见面试题

**Q1：Pydantic v1 和 v2 的主要区别是什么？FastAPI 如何处理兼容性问题？**

> Pydantic v2 的核心变化包括：① **性能提升**：校验引擎用 Rust 重写，速度提升 5-50 倍；② **API 重命名**：`dict()` → `model_dump()`、`json()` → `model_dump_json()`、`parse_obj()` → `model_validate()`、`__fields__` → `model_fields`；③ **校验器装饰器**：`@validator` 改为 `@field_validator`，新增 `@model_validator`；④ **Config 方式**：从嵌套类改为 `model_config = ConfigDict(...)`。FastAPI 0.100+ 完全适配 v2，若项目仍使用 v1，可安装 `pydantic v1` 或 `fastapi` 早期版本，但建议迁移到 v2 以获得性能收益。

**Q2：如何在 Pydantic 中实现字段间的联合校验（如密码和确认密码）？**

> 使用 `@model_validator` 装饰器（v2）或 `@root_validator`（v1）。`@model_validator` 支持两种模式：`mode='before'` 在校验之前接收原始字典数据，`mode='after'` 在字段校验之后接收已实例化的模型对象。例如校验密码一致性时，可用 `mode='after'` 访问 `self.password` 和 `self.confirm_password`，若不一致则抛出 `ValueError`，Pydantic 会自动将其转换为用户友好的校验错误响应。

---

## 4. 依赖注入系统（Depends、子依赖、依赖覆盖）

FastAPI 的依赖注入（Dependency Injection, DI）系统是其架构设计的精髓所在。它允许开发者将可复用的逻辑（如数据库连接获取、权限校验、通用参数解析）封装为"依赖函数"，然后在路由中通过 `Depends()` 声明使用。这种设计遵循了面向对象编程中的"控制反转"（IoC）原则，实现了关注点分离和代码复用。

**基础依赖**：任何可调用对象（函数、类、lambda）都可以作为依赖。依赖函数本身也可以使用 `Depends()` 声明子依赖，形成依赖链。FastAPI 会自动处理依赖的解析顺序，确保子依赖先于父依赖执行。依赖函数的返回值会被注入到路由处理函数的对应参数中。

**子依赖**：当依赖 A 的函数签名中包含 `Depends(B)` 时，B 就是 A 的子依赖。FastAPI 会递归解析整个依赖树。这一特性非常适合分层架构——例如 `get_current_user` 依赖 `get_db`，`require_admin` 依赖 `get_current_user`。

**依赖覆盖（Override）**：在测试环境中，经常需要替换真实依赖为 Mock。FastAPI 提供了 `app.dependency_overrides` 字典，可以将任何依赖函数映射到替代实现。这在单元测试中极为实用，无需修改业务代码即可切换数据库、外部服务等依赖项。

**类作为依赖**：除了函数，类也可以作为依赖。FastAPI 会实例化该类并将实例注入。这在需要维护状态时特别有用（虽然状态ful依赖在并发环境下需谨慎使用）。

**依赖作用域**：默认情况下，每个请求都会独立解析依赖。但 FastAPI 也支持 `yield` 语法的依赖，用于资源管理（如数据库会话的生命周期控制）。

```python
from fastapi import FastAPI, Depends, HTTPException, status
from typing import Optional, Generator
from contextlib import contextmanager

app = FastAPI()

# ========== 模拟数据库和模型 ==========
class Database:
    """模拟数据库连接"""
    def __init__(self):
        self.connected = False
    def connect(self):
        self.connected = True
        return self
    def disconnect(self):
        self.connected = False
    def query(self, sql: str):
        return {"sql": sql, "result": "mock_data"}

class User:
    """用户模型"""
    def __init__(self, id: int, username: str, is_admin: bool = False):
        self.id = id
        self.username = username
        self.is_admin = is_admin

# ========== 基础依赖：数据库连接 ==========
def get_db() -> Generator[Database, None, None]:
    """
    数据库会话依赖（yield 形式）
    - 请求开始时创建连接
    - 请求结束时自动关闭
    - 即使发生异常也会执行 finally 块
    """
    db = Database()
    try:
        yield db.connect()
    finally:
        db.disconnect()

# ========== 子依赖：获取当前用户 ==========
async def get_current_user(
    token: Optional[str] = None,  # 简化版，实际应从 Header 解析 JWT
    db: Database = Depends(get_db)
) -> User:
    """
    子依赖：依赖 get_db
    根据 token 获取当前登录用户
    """
    if token is None:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    # 模拟查询数据库
    if token == "valid_token":
        return User(id=1, username="admin", is_admin=True)
    raise HTTPException(status_code=401, detail="无效的认证令牌")

# ========== 子依赖的嵌套：管理员权限校验 ==========
async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    子依赖：依赖 get_current_user
    校验当前用户是否为管理员
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user

# ========== 路由中使用依赖 ==========
@app.get("/public")
async def public_endpoint():
    """公开接口，无需认证"""
    return {"message": "这是公开接口"}

@app.get("/profile")
async def user_profile(current_user: User = Depends(get_current_user)):
    """需要登录的接口"""
    return {"user_id": current_user.id, "username": current_user.username}

@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin)  # 需要管理员权限
):
    """删除用户（仅管理员可访问）"""
    return {"message": f"用户 {user_id} 已被管理员 {admin.username} 删除"}

@app.get("/data")
async def get_data(db: Database = Depends(get_db)):
    """使用数据库依赖"""
    result = db.query("SELECT * FROM items")
    return result

# ========== 依赖覆盖（用于测试） ==========
def mock_get_db():
    """Mock 数据库依赖"""
    class MockDB:
        def query(self, sql: str):
            return {"mock": True, "data": []}
    return MockDB()

# 在测试代码中启用覆盖：
# app.dependency_overrides[get_db] = mock_get_db

# 也可以在路由级别覆盖：
@app.get("/test-db")
async def test_with_mock(db: Database = Depends(get_db)):
    return db.query("SELECT 1")

# 运行测试前设置：
# app.dependency_overrides[get_db] = mock_get_db
# try:
#     client.get("/test-db")
# finally:
#     app.dependency_overrides.pop(get_db, None)  # 清理覆盖
```

### 常见面试题

**Q1：FastAPI 的依赖注入与 Flask 的 `before_request` / 装饰器模式相比有何优势？**

> 优势体现在三个层面：① **组合性**：依赖可以像乐高积木一样自由组合和嵌套，而装饰器模式容易出现嵌套地狱；② **显式性**：依赖关系在函数签名中一目了然，便于静态分析和 IDE 自动补全，而装饰器的逻辑往往隐藏在内部；③ **可测试性**：`dependency_overrides` 允许在测试中精确替换任意依赖，而装饰器模式需要在模块级别 Mock 或修改导入；④ **类型安全**：依赖的返回值类型被正确推断，IDE 和 mypy 可以全程追踪。

**Q2：`Depends` 中使用普通函数和 `yield` 函数有什么区别？**

> 普通 `def`/`async def` 依赖函数在每次请求时执行并返回结果；`yield` 形式的依赖函数则支持**上下文管理器模式**——`yield` 之前的代码在请求开始时执行（如创建数据库连接），`yield` 返回资源对象供路由使用，`yield` 之后的代码在响应返回后执行（如关闭连接、提交/回滚事务）。这在需要管理资源生命周期的场景（数据库会话、锁、事务）中不可或缺。`yield` 依赖还支持异常传播，如果路由抛出异常，可以在 finally 块中执行清理逻辑。

---

## 5. 中间件与异常处理（自定义中间件、HTTPException、全局异常处理器）

中间件（Middleware）是 ASGI 应用的核心机制，它以一种"洋葱模型"（Onion Model）在请求到达路由处理函数之前和响应返回客户端之后插入自定义逻辑。FastAPI 基于 Starlette 的中间件系统，支持全局中间件和路由级中间件。

**自定义中间件**：FastAPI 支持两种创建中间件的方式：① 使用 `@app.middleware("http")` 装饰器；② 继承 `BaseHTTPMiddleware` 类。装饰器方式更轻量，适合简单场景；类方式更适合复杂逻辑和状态管理。中间件中可以进行：请求日志记录、耗时统计、CORS 处理、请求 ID 追踪、限流、认证前置校验等。

**HTTPException**：FastAPI 内置的异常类，用于在业务逻辑中主动抛出 HTTP 错误。它支持自定义状态码、详情信息和响应头。抛出 `HTTPException` 后，FastAPI 会自动将其转换为对应的 JSON 错误响应，无需手动构造 `Response`。

**全局异常处理器**：通过 `@app.exception_handler()` 装饰器注册自定义异常处理器，可以捕获特定异常类型并统一格式化错误响应。这在生产环境中极为重要——可以将所有未处理的异常转换为统一的错误响应结构，同时记录详细日志，避免将内部堆栈信息暴露给客户端（安全风险）。

**异常处理优先级**：FastAPI 的异常处理遵循"最近匹配"原则。自定义的 `exception_handler` 优先于默认处理器，路由级别的 `try/except` 优先于全局处理器。合理利用这一优先级可以实现精细化的错误管理策略。

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
import traceback
import uuid

app = FastAPI()

# ========== 1. CORS 中间件（内置）==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 2. 自定义中间件：请求日志 + 耗时统计 ==========
class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件：记录每个请求的耗时和状态码"""
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id  # 将 request_id 存入 state，供后续使用
        
        start_time = time.time()
        print(f"[{request_id}] → {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}s"
            print(f"[{request_id}] ← {response.status_code} ({process_time:.3f}s)")
            return response
        except Exception as e:
            process_time = time.time() - start_time
            print(f"[{request_id}] ✕ ERROR: {e} ({process_time:.3f}s)")
            raise

app.add_middleware(LoggingMiddleware)

# ========== 3. 装饰器形式中间件：请求体大小限制 ==========
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """限制请求体大小（示例：10MB）"""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": "请求体过大，限制10MB"}
        )
    return await call_next(request)

# ========== 4. 业务路由 ==========
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    if item_id <= 0:
        # 主动抛出 HTTP 异常
        raise HTTPException(
            status_code=400,
            detail="商品ID必须为正整数",
            headers={"X-Error": "invalid_item_id"}
        )
    if item_id > 10000:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"item_id": item_id}

# ========== 5. 自定义业务异常 ==========
class BusinessException(Exception):
    """业务异常基类"""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class ResourceNotFoundException(BusinessException):
    """资源不存在异常"""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} '{resource_id}' 不存在",
            status_code=404
        )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    # 模拟业务异常
    if not order_id.startswith("ORD"):
        raise BusinessException(code="INVALID_ORDER_ID", message="订单编号格式错误")
    if order_id == "ORD999":
        raise ResourceNotFoundException("订单", order_id)
    return {"order_id": order_id}

# ========== 6. 全局异常处理器 ==========
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    """业务异常处理器：统一格式化"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": exc.code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", None),
            "path": str(request.url.path)
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局兜底异常处理器
    - 生产环境不应暴露内部堆栈
    - 将详细错误记录到日志系统
    """
    request_id = getattr(request.state, "request_id", "unknown")
    error_trace = traceback.format_exc()
    # 实际项目中这里应该写入日志系统（如 Sentry、ELK）
    print(f"[ERROR][{request_id}] 未捕获异常:\n{error_trace}")
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误，请稍后重试",
            "request_id": request_id
            # 注意：生产环境不要返回 traceback
        }
    )
```

### 常见面试题

**Q1：FastAPI 中间件的执行顺序是怎样的？如何控制中间件的加载顺序？**

> FastAPI 的中间件遵循"洋葱模型"（Onion Model）执行顺序。对于中间件 A、B、C（按添加顺序），请求阶段的执行顺序是 A → B → C → 路由处理函数，响应阶段的执行顺序是 路由处理函数 → C → B → A。这意味着先添加的中间件在最外层，后添加的在内层。`app.add_middleware()` 的调用顺序决定了中间件的嵌套层次——先调用的包裹后调用的。如果需要精确控制顺序，应按照从外到内的顺序依次调用 `add_middleware`。

**Q2：如何在 FastAPI 中实现统一的 API 错误响应格式？**

> 最佳实践是三层异常处理策略：① **业务异常**：定义自定义业务异常类（如 `BusinessException`），继承自 `Exception`，携带 `code`、`message`、`status_code` 等属性，通过 `@app.exception_handler(BusinessException)` 注册处理器统一格式化；② **HTTPException**：FastAPI 内置异常，可通过自定义处理器覆盖默认行为；③ **兜底异常**：用 `@app.exception_handler(Exception)` 捕获所有未处理异常，返回统一的 500 错误响应，同时将详细堆栈记录到日志系统。生产环境中务必注意：**永远不要将 traceback 返回给客户端**，这是严重的信息泄露风险。

---

## 6. 后台任务（BackgroundTasks、Celery 集成）

Web 接口的响应时间直接影响用户体验，但某些操作（发送邮件、生成报表、图片处理、数据同步）天然耗时较长，不适合在请求处理线程/协程中同步执行。FastAPI 提供了 `BackgroundTasks` 用于简单的异步任务卸载，同时与 Celery 等分布式任务队列无缝集成，满足复杂场景需求。

**BackgroundTasks**：FastAPI 内置的后台任务机制，基于 Starlette 的 `BackgroundTask`。在路由函数中注入 `BackgroundTasks` 对象，调用 `add_task(func, *args, **kwargs)` 注册任务。请求响应返回后，FastAPI 会在后台执行这些任务。注意：BackgroundTasks 运行在**同一个进程**中，如果进程重启，未执行的任务会丢失。因此它适合轻量级、可容忍丢失的任务，不适合关键业务逻辑。

**Celery 集成**：对于需要可靠性保证、分布式执行、任务重试、定时调度的场景，Celery 是行业标准方案。FastAPI 与 Celery 的结合模式通常是：FastAPI 接收 HTTP 请求后，将任务发送到 Celery Broker（Redis/RabbitMQ），立即返回任务 ID；Celery Worker 从 Broker 获取任务并异步执行；客户端通过任务 ID 查询执行状态和结果。这种架构实现了 HTTP 接口与耗时任务的完全解耦。

**任务状态查询**：Celery 提供了 `AsyncResult` 对象，可以查询任务的 `PENDING`、`SUCCESS`、`FAILURE`、`RETRY` 等状态，以及获取返回值或异常信息。

```python
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr
from celery import Celery
from celery.result import AsyncResult
import time

app = FastAPI()

# ========== Celery 配置 ==========
celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",      # 消息队列
    backend="redis://localhost:6379/1"       # 结果存储
)

@celery_app.task(bind=True, max_retries=3)
def send_email_task(self, to_email: str, subject: str, body: str):
    """
    Celery 任务：发送邮件
    - bind=True 使 self 可用，支持 self.retry()
    - max_retries=3 失败时自动重试3次
    """
    try:
        print(f"[Celery] 正在发送邮件到 {to_email}...")
        time.sleep(2)  # 模拟发送耗时
        # 模拟偶发失败
        import random
        if random.random() < 0.3:
            raise Exception("邮件服务暂时不可用")
        print(f"[Celery] 邮件发送成功: {to_email}")
        return {"status": "sent", "to": to_email}
    except Exception as exc:
        print(f"[Celery] 发送失败，准备重试: {exc}")
        raise self.retry(exc=exc, countdown=5)  # 5秒后重试

@celery_app.task
def generate_report_task(user_id: int, report_type: str):
    """Celery 任务：生成报表"""
    print(f"[Celery] 为用户 {user_id} 生成 {report_type} 报表...")
    time.sleep(5)  # 模拟复杂计算
    return {"user_id": user_id, "report_url": f"/reports/{user_id}.pdf"}

# ========== BackgroundTasks：轻量级后台任务 ==========
def write_log(message: str):
    """模拟写日志（轻量级任务）"""
    with open("app.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

@app.post("/notify")
async def send_notification(
    email: EmailStr,
    background_tasks: BackgroundTasks
):
    """
    发送通知接口
    - 使用 BackgroundTasks 记录日志（轻量、可容忍丢失）
    - 使用 Celery 发送邮件（需要可靠性保证）
    """
    # 注册后台任务：请求响应后立即执行
    background_tasks.add_task(write_log, f"发送通知到 {email}")
    
    # 派发 Celery 任务：交由 Worker 异步执行
    task = send_email_task.delay(email, "欢迎邮件", "欢迎注册我们的服务！")
    
    return {
        "message": "通知已提交",
        "email_task_id": task.id,
        "status": "queued"
    }

# ========== 查询 Celery 任务状态 ==========
@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """查询异步任务执行状态"""
    task_result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": task_result.status,
    }
    
    if task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.result)
    
    return response

# ========== 更复杂的场景：报表生成 ==========
class ReportRequest(BaseModel):
    user_id: int
    report_type: str = "monthly"  # monthly, weekly, daily

@app.post("/reports")
async def create_report(request: ReportRequest):
    """提交报表生成任务"""
    task = generate_report_task.delay(request.user_id, request.report_type)
    return {
        "task_id": task.id,
        "status": "queued",
        "check_url": f"/tasks/{task.id}"
    }

# ========== 启动 Celery Worker 的命令 ==========
# celery -A main.celery_app worker --loglevel=info --concurrency=4
# 或使用 flower 监控：celery -A main.celery_app flower --port=5555
```

### 常见面试题

**Q1：BackgroundTasks 和 Celery 各适用于什么场景？它们的本质区别是什么？**

> **BackgroundTasks** 适合轻量级、非关键的后台操作（如写日志、更新缓存、轻量通知），它的特点是实现简单、无需额外基础设施，但任务存储在**内存**中，服务重启即丢失，且无法分布式执行。**Celery** 适合关键业务、耗时操作、需要可靠性和分布式扩展的场景（如发送邮件、生成报表、批量数据处理），它通过 Broker（Redis/RabbitMQ）持久化任务，支持任务重试、定时调度（beat）、结果存储、分布式 Worker 和消费速率控制。本质区别在于：BackgroundTasks 是进程内的协程调度，Celery 是跨进程的分布式消息队列系统。

**Q2：FastAPI 中如何安全地关闭正在进行的后台任务？**

> 对于 BackgroundTasks，由于它运行在 ASGI 服务器进程内，服务关闭时会等待当前请求处理完成，但已注册尚未执行的后台任务可能会丢失。如果需要优雅关闭，应考虑使用 Celery 等外部队列。对于 Celery，Worker 支持**优雅关闭**（Graceful Shutdown）：发送 `SIGTERM` 信号后，Worker 会停止接收新任务，但会等待当前正在执行的任务完成（可配置超时）。在 Docker/K8s 环境中，应设置合理的 `terminationGracePeriodSeconds`，确保任务有充足时间完成。此外，Celery 任务的 `acks_late=True` 配置可以确保任务执行完成后再确认（ack），防止任务在 Worker 崩溃时丢失。

---

## 7. WebSocket 支持

WebSocket 是一种全双工通信协议，允许服务器主动向客户端推送数据，极大地提升了实时应用的开发体验。FastAPI 基于 Starlette 提供了原生 WebSocket 支持，可以同时处理 HTTP 和 WebSocket 连接，是构建实时聊天、在线协作、实时监控、股票行情推送等应用的理想选择。

**WebSocket 生命周期**：WebSocket 连接的生命周期包括：① **握手阶段**：客户端发送 HTTP Upgrade 请求，服务器响应 101 Switching Protocols；② **连接建立**：连接升级为 WebSocket，双方可以双向发送消息；③ **消息传输**：文本消息（`send_text`/`receive_text`）和二进制消息（`send_bytes`/`receive_bytes`）；④ **连接关闭**：任一方发送关闭帧，或网络断开。

**FastAPI 的 WebSocket 类**：`WebSocket` 对象提供 `accept()`（接受连接）、`receive_text()`/`receive_json()`（接收消息）、`send_text()`/`send_json()`（发送消息）、`close()`（关闭连接）等方法。在 `accept()` 之前，连接处于 HTTP 握手阶段；之后进入全双工通信状态。

**连接管理**：生产环境中需要管理活跃的 WebSocket 连接，通常使用"连接管理器"（Connection Manager）模式：维护一个全局的连接集合（set/list），新连接加入时注册，断开时移除，广播消息时遍历所有连接发送。

**心跳与断开检测**：WebSocket 连接可能因网络波动静默断开。需要实现心跳机制（ping/pong），或利用 WebSocket 协议内置的 ping/pong 帧。Starlette/FastAPI 底层会自动处理协议级 ping/pong，但应用级的心跳（如定期发送 `{"type": "ping"}`）对检测僵尸连接仍然必要。

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import asyncio

app = FastAPI()

# ========== 连接管理器 ==========
class ConnectionManager:
    """
    WebSocket 连接管理器
    - 维护所有活跃连接
    - 支持按房间/频道分组（扩展功能）
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # 按用户ID分组（用于定向推送）
        self.user_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int = None):
        """接受新连接并注册"""
        await websocket.accept()
        self.active_connections.append(websocket)
        if user_id:
            self.user_connections[user_id] = websocket
        print(f"[WebSocket] 新连接建立，当前在线: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: int = None):
        """移除断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if user_id and user_id in self.user_connections:
            del self.user_connections[user_id]
        print(f"[WebSocket] 连接断开，当前在线: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """广播消息给所有连接"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        # 清理已断开的连接
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to_user(self, user_id: int, message: str):
        """定向发送给特定用户"""
        if user_id in self.user_connections:
            await self.user_connections[user_id].send_text(message)

manager = ConnectionManager()

# ========== WebSocket 路由 ==========
@app.websocket("/ws/chat/{room_id}")
async def websocket_chat(websocket: WebSocket, room_id: str):
    """
    聊天室 WebSocket 接口
    - 支持接收和广播消息
    - 自动处理连接和断开
    """
    await manager.connect(websocket)
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "type": "system",
            "message": f"欢迎进入聊天室 {room_id}！"
        })
        
        while True:
            # 等待客户端消息
            data = await websocket.receive_text()
            
            try:
                message_data = json.loads(data)
                username = message_data.get("username", "匿名")
                content = message_data.get("content", "")
                
                # 构建广播消息
                broadcast_msg = json.dumps({
                    "type": "message",
                    "room_id": room_id,
                    "username": username,
                    "content": content,
                    "timestamp": asyncio.get_event_loop().time()
                }, ensure_ascii=False)
                
                # 广播给聊天室所有人
                await manager.broadcast(broadcast_msg)
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "消息格式错误，请发送 JSON"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({
            "type": "system",
            "message": "有用户离开了聊天室"
        }, ensure_ascii=False))

@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, user_id: int = 0):
    """
    个人通知推送 WebSocket
    - 模拟服务器主动推送
    """
    await manager.connect(websocket, user_id)
    try:
        # 发送历史通知
        await websocket.send_json({
            "type": "notification",
            "data": "您有 3 条未读消息"
        })
        
        # 模拟定期推送（心跳 + 通知）
        while True:
            await asyncio.sleep(30)  # 每30秒
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": asyncio.get_event_loop().time()
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        print(f"[WebSocket] 通知连接异常: {e}")
        manager.disconnect(websocket, user_id)

# ========== 主动推送接口（HTTP 触发 WebSocket 推送）==========
@app.post("/push-notification")
async def push_notification(user_id: int, message: str):
    """通过 HTTP 接口触发 WebSocket 推送"""
    await manager.send_to_user(user_id, json.dumps({
        "type": "notification",
        "message": message
    }, ensure_ascii=False))
    return {"status": "pushed"}

# ========== 前端连接示例（JavaScript）==========
# const ws = new WebSocket("ws://localhost:8000/ws/chat/room1");
# ws.onopen = () => console.log("已连接");
# ws.onmessage = (event) => console.log("收到:", JSON.parse(event.data));
# ws.send(JSON.stringify({username: "张三", content: "大家好！"}));
```

### 常见面试题

**Q1：WebSocket 与 HTTP 长轮询（Long Polling）相比有什么优劣？**

> **WebSocket 优势**：① **真正的全双工**：服务器可以随时主动推送，无需客户端周期性请求；② **低延迟**：建立连接后，消息帧头部仅 2-14 字节，远低于 HTTP 的请求/响应头；③ **减少连接开销**：一次握手后持续复用连接，避免 HTTP 的重复 TCP/TLS 握手。**劣势**：① **复杂度更高**：需要处理连接状态管理、心跳、重连、并发安全；② **代理/防火墙兼容性**：某些企业级代理可能不支持 WebSocket Upgrade；③ **无状态性挑战**：WebSocket 连接是有状态的，水平扩展时需要共享连接信息（通常使用 Redis Pub/Sub）。长轮询实现简单、兼容性好，但延迟高、服务器资源占用大，适合简单场景或兼容性要求高的环境。

**Q2：FastAPI 中如何实现 WebSocket 的鉴权？**

> WebSocket 握手阶段本质上是 HTTP 请求，因此可以在 `accept()` 之前进行鉴权：① **查询参数传递 Token**：`ws://host/ws?token=xxx`，在 `websocket.accept()` 之前读取 `websocket.query_params` 并校验 JWT；② **Cookie 鉴权**：读取 `websocket.cookies` 中的 Session ID 或 Token；③ **Header 鉴权**：某些客户端支持在 WebSocket 握手时附加 Header（如 `Sec-WebSocket-Protocol`）。如果鉴权失败，直接调用 `websocket.close(code=1008, reason="Unauthorized")` 拒绝连接。**注意**：不要在 WebSocket 连接建立后仅在应用层校验身份，这会导致未授权连接长时间占用服务器资源。

---

## 8. OAuth2 + JWT 认证（密码模式、Bearer Token）

认证与授权是 Web 应用安全的核心环节。FastAPI 内置了完整的 OAuth2 支持，包括密码模式（Password Flow）、客户端模式（Client Credentials）、授权码模式（Authorization Code）等。配合 JWT（JSON Web Token），可以快速构建生产级的认证系统。

**OAuth2 密码模式**：适用于第一方应用（如官方 Web/App），用户直接输入用户名和密码换取 Access Token。流程为：① 客户端发送 `username` + `password` 到 `/token` 端点；② 服务器校验凭据后签发 JWT；③ 客户端在后续请求的 `Authorization: Bearer <token>` 头中携带 JWT；④ 服务器验证 JWT 的有效性和签名。

**JWT 结构**：JWT 由三部分组成，用 `.` 分隔：`Header.Payload.Signature`。Header 包含算法信息，Payload 包含声明（claims，如 `sub` 用户标识、`exp` 过期时间、`iat` 签发时间），Signature 是 Header + Payload 的签名，防止篡改。

**FastAPI 的 OAuth2 工具**：`OAuth2PasswordBearer` 类声明 Token 获取端点 URL，`OAuth2PasswordRequestForm` 封装了标准的密码模式请求表单。`Depends(get_current_user)` 模式将认证逻辑封装为可复用依赖。

**密码安全**：绝对禁止明文存储密码。应使用 `passlib` 库的 bcrypt 算法对密码进行哈希，校验时比较哈希值。bcrypt 自动包含盐值（salt）和成本因子（cost factor），可以有效抵御彩虹表攻击。

```python
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt

app = FastAPI()

# ========== 安全配置 ==========
SECRET_KEY = "your-super-secret-key-change-in-production"  # 生产环境使用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 方案：指定 Token 获取端点
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# ========== 数据模型 ==========
class User(BaseModel):
    """用户模型（返回给客户端，不含密码）"""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: bool = False

class UserInDB(User):
    """数据库中的用户模型（包含密码哈希）"""
    hashed_password: str

class Token(BaseModel):
    """Token 响应模型"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int

# ========== 模拟用户数据库 ==========
fake_users_db = {
    "admin": {
        "username": "admin",
        "full_name": "管理员",
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("admin123"),
        "disabled": False,
    },
    "user": {
        "username": "user",
        "full_name": "普通用户",
        "email": "user@example.com",
        "hashed_password": pwd_context.hash("user123"),
        "disabled": False,
    }
}

# ========== 工具函数 ==========
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希密码是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db: dict, username: str) -> Optional[UserInDB]:
    """从数据库获取用户"""
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)
    return None

def authenticate_user(db: dict, username: str, password: str) -> Optional[UserInDB]:
    """认证用户：校验用户名和密码"""
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT Access Token
    - data: 要编码到 Token 中的数据（通常包含用户标识 sub）
    - expires_delta: 过期时间增量，默认30分钟
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ========== 依赖：获取当前用户 ==========
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    从 Bearer Token 中解析当前用户
    - 被保护的路由通过 Depends(get_current_user) 使用
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise credentials_exception
    
    user = get_user(fake_users_db, username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """校验用户是否被禁用"""
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return current_user

# ========== 路由 ==========
@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 密码模式登录接口
    - 接收 username + password（表单格式）
    - 校验通过后返回 JWT Token
    """
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """获取当前登录用户信息"""
    return current_user

@app.get("/admin/dashboard")
async def admin_dashboard(current_user: User = Depends(get_current_active_user)):
    """管理员仪表盘（示例：可扩展权限检查）"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return {"message": "管理员仪表盘", "stats": {"users": 100, "orders": 500}}

# ========== 使用示例（curl）==========
# 1. 登录获取 Token：
# curl -X POST "http://localhost:8000/token" \
#   -H "Content-Type: application/x-www-form-urlencoded" \
#   -d "username=admin&password=admin123"
#
# 2. 访问受保护接口：
# curl -H "Authorization: Bearer <access_token>" \
#   http://localhost:8000/users/me
```

### 常见面试题

**Q1：JWT 的优缺点是什么？为什么说 JWT 不适合存储敏感信息？**

> **优点**：① 无状态，服务器无需存储 Session，天然支持分布式和水平扩展；② 自包含，Token 中携带了用户标识和权限信息，减少数据库查询；③ 跨域友好，适合微服务和前后端分离架构。**缺点**：① **无法主动失效**：一旦签发，在过期前无法撤销（除非维护黑名单，但这破坏了无状态性）；② **Payload 可解码**：JWT 的 Header 和 Payload 只是 Base64Url 编码，任何人都可以解码查看内容（只是无法篡改），因此**绝对不能在 Payload 中存储密码、身份证号等敏感信息**；③ **体积较大**：相比 Session ID，JWT 通常几百字节，大量请求会增加带宽开销。**安全实践**：使用短过期时间（15-30 分钟），配合 Refresh Token 机制；HTTPS 传输；密钥定期轮换。

**Q2：FastAPI 中如何实现 Refresh Token 机制？**

> Refresh Token 机制的核心思想是：Access Token 有效期短（如 15 分钟），用于常规 API 访问；Refresh Token 有效期长（如 7 天），仅用于获取新的 Access Token。实现步骤：① 登录时同时签发 Access Token 和 Refresh Token，Refresh Token 存储到数据库/Redis；② 客户端在 Access Token 过期后，携带 Refresh Token 调用 `/refresh` 端点；③ 服务器校验 Refresh Token 的有效性（签名 + 数据库存在性 + 未撤销）；④ 签发新的 Access Token，可选择同时轮换 Refresh Token（增强安全性）；⑤ 用户登出时，将 Refresh Token 标记为失效（存入 Redis 黑名单或从数据库删除）。这种模式在安全性（短效 Token）和用户体验（无需频繁登录）之间取得了平衡。

---

## 9. 事件系统（startup/shutdown 事件、lifespan）

Web 应用在启动和关闭时经常需要执行一些初始化或清理操作：建立数据库连接池、加载缓存、注册服务发现、关闭文件句柄等。FastAPI 提供了事件系统来管理应用生命周期的各个阶段。

**传统事件（@app.on_event）**：FastAPI 早期版本使用 `@app.on_event("startup")` 和 `@app.on_event("shutdown")` 装饰器注册启动和关闭事件。这些事件处理器在应用启动时和关闭时分别执行。可以注册多个事件处理器，它们会按照注册顺序执行。

**Lifespan（推荐方式）**：从 FastAPI 0.93+ 开始，官方推荐使用 ASGI 标准的 `lifespan` 协议替代传统事件。`lifespan` 使用 Python 的上下文管理器（`@asynccontextmanager`）语义，将启动和关闭逻辑封装在一个地方，代码更加紧凑和清晰。`lifespan` 函数在 `yield` 之前执行启动逻辑，在 `yield` 之后执行关闭逻辑，即使启动失败或运行时异常也能保证关闭逻辑被执行。

**适用场景**：数据库连接池初始化、Redis 连接建立、加载配置和预热缓存、注册/注销服务发现（Consul/Eureka）、启动后台任务调度器、关闭时优雅释放资源。

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import aioredis
import asyncpg

# ========== 全局状态（应用级别共享资源）==========
class AppState:
    """应用状态管理"""
    db_pool = None
    redis_client = None
    config = {}

# ========== 现代方式：Lifespan（推荐）==========
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理器
    - yield 之前：启动阶段
    - yield 之后：关闭阶段
    - 即使启动失败，关闭逻辑也会执行
    """
    # ===== 启动阶段 =====
    print("[Lifespan] 应用启动中...")
    
    # 1. 加载配置
    AppState.config = {
        "database_url": "postgresql://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "max_connections": 20
    }
    print(f"[Lifespan] 配置加载完成: {AppState.config}")
    
    # 2. 建立数据库连接池
    try:
        # 使用 asyncpg 创建 PostgreSQL 连接池
        AppState.db_pool = await asyncpg.create_pool(
            AppState.config["database_url"],
            min_size=5,
            max_size=AppState.config["max_connections"]
        )
        print("[Lifespan] 数据库连接池已创建")
    except Exception as e:
        print(f"[Lifespan] 数据库连接失败: {e}")
        raise  # 启动失败，阻止应用启动
    
    # 3. 建立 Redis 连接
    try:
        AppState.redis_client = await aioredis.from_url(
            AppState.config["redis_url"],
            encoding="utf-8",
            decode_responses=True
        )
        await AppState.redis_client.ping()
        print("[Lifespan] Redis 连接已建立")
    except Exception as e:
        print(f"[Lifespan] Redis 连接失败: {e}")
        raise
    
    # 4. 预热缓存（示例）
    await AppState.redis_client.set("app:start_time", __import__('time').time())
    print("[Lifespan] 启动完成，应用就绪")
    
    # yield 将控制权交给 FastAPI，应用开始接收请求
    yield
    
    # ===== 关闭阶段 =====
    print("[Lifespan] 应用关闭中...")
    
    # 1. 关闭数据库连接池
    if AppState.db_pool:
        await AppState.db_pool.close()
        print("[Lifespan] 数据库连接池已关闭")
    
    # 2. 关闭 Redis 连接
    if AppState.redis_client:
        await AppState.redis_client.close()
        print("[Lifespan] Redis 连接已关闭")
    
    print("[Lifespan] 资源清理完成，应用已关闭")

# 使用 lifespan 创建应用
app = FastAPI(lifespan=lifespan)

# ========== 传统方式（兼容旧版本）==========
# @app.on_event("startup")
# async def startup_event():
#     print("[Startup] 应用启动")
# 
# @app.on_event("shutdown")
# async def shutdown_event():
#     print("[Shutdown] 应用关闭")

# ========== 在路由中使用应用级资源 ==========
@app.get("/health")
async def health_check():
    """健康检查接口"""
    health = {
        "status": "healthy",
        "database": False,
        "redis": False
    }
    
    if AppState.db_pool:
        try:
            async with AppState.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health["database"] = True
        except Exception:
            pass
    
    if AppState.redis_client:
        try:
            await AppState.redis_client.ping()
            health["redis"] = True
        except Exception:
            pass
    
    return health

@app.get("/config")
async def get_config():
    """获取应用配置（仅示例，生产环境不应暴露敏感配置）"""
    # 过滤敏感信息
    safe_config = {k: v for k, v in AppState.config.items() if "password" not in k and "secret" not in k}
    return safe_config
```

### 常见面试题

**Q1：`@app.on_event` 和 `lifespan` 有什么区别？为什么推荐后者？**

> 主要区别有三点：① **语义完整性**：`lifespan` 使用上下文管理器将启动和关闭逻辑封装在一起，代码内聚性更强，而 `@app.on_event` 将两者分离，容易遗漏配对；② **异常安全**：`lifespan` 中即使启动阶段发生异常，`yield` 之后的关闭逻辑仍然可以通过 `try/finally` 保证执行（因为 `@asynccontextmanager` 会自动处理），而多个分散的 `@app.on_event` 难以保证这种原子性；③ **ASGI 标准兼容**：`lifespan` 是 ASGI 协议的标准生命周期事件，被 Uvicorn、Hypercorn 等服务器原生支持，而 `@app.on_event` 是 Starlette 的扩展机制。FastAPI 官方已明确推荐使用 `lifespan`，`@app.on_event` 在新版本中标记为弃用。

**Q2：如果启动阶段数据库连接失败，应该如何处理？**

> 正确的处理策略是**快速失败（Fail Fast）**：在 `lifespan` 的启动阶段，如果核心依赖（如数据库、Redis、消息队列）连接失败，应该直接抛出异常，阻止应用启动。这比应用启动后才发现连接不可用要好得多——可以避免流量接入后的大量错误，也便于容器编排系统（K8s）检测到启动失败并触发重启或告警。具体实现：① 在 `lifespan` 中使用 `try/except` 捕获连接异常；② 记录详细错误日志；③ `raise` 重新抛出异常；④ 配合 Docker/K8s 的健康检查，让平台自动处理失败状态。对于非核心依赖（如统计服务），可以降级启动并持续重试，而不是阻止主应用启动。

---

## 10. 性能优化（异步数据库、连接池、缓存）

FastAPI 的异步架构为高性能后端服务奠定了基础，但要充分发挥其优势，还需要在数据库访问、连接管理和缓存策略等层面进行系统性优化。

**异步数据库**：Python 生态中主流的异步 ORM 和驱动包括：`SQLAlchemy 1.4+`（支持 asyncio）、`Tortoise ORM`（Django-like 语法，原生异步）、`Prisma Client Python`、`asyncpg`（PostgreSQL 原生异步驱动）、`aiomysql`（MySQL 异步驱动）。使用异步数据库的关键是**全程避免同步调用**——包括避免在异步路由中使用 `time.sleep()`、`requests` 库等阻塞操作，应替换为 `asyncio.sleep()`、`httpx` 等异步替代方案。

**连接池**：数据库连接是昂贵的资源（TCP 握手 + 认证），频繁创建销毁会严重影响性能。连接池（Connection Pool）维护一组可复用的连接，请求到来时借用，完成后归还。`asyncpg` 和 `SQLAlchemy` 都内置了连接池管理，关键参数包括 `pool_size`（最小连接数）、`max_overflow`（最大溢出连接）、`pool_timeout`（获取连接超时）、`pool_recycle`（连接回收时间，防止数据库端超时断开）。

**缓存策略**：缓存是性能优化的银弹。常见策略包括：① **本地缓存**：`cachetools`、`functools.lru_cache`，适合读多写少、数据量小、一致性要求不高的场景；② **分布式缓存**：Redis/Memcached，适合多实例共享、需要 TTL 过期、数据量大的场景；③ **HTTP 缓存**：通过 `Cache-Control`、`ETag`、`Last-Modified` 响应头让浏览器/CDN 缓存；④ **数据库查询缓存**：ORM 的查询结果缓存，或使用 Redis 缓存热点查询。缓存设计需要重点考虑**缓存穿透**（查询不存在的数据）、**缓存击穿**（热点 key 过期瞬间大量请求穿透）、**缓存雪崩**（大量 key 同时过期）等问题。

```python
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, select
from redis.asyncio import Redis
from functools import lru_cache
import asyncio
import time

app = FastAPI()

# ========== 1. 异步数据库配置（SQLAlchemy + asyncpg）==========
DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/testdb"

# 创建异步引擎，启用连接池
engine = create_async_engine(
    DATABASE_URL,
    echo=False,                    # 设为 True 可查看 SQL 日志
    pool_size=10,                  # 连接池最小连接数
    max_overflow=20,               # 最大溢出连接数
    pool_timeout=30,               # 获取连接超时时间（秒）
    pool_recycle=1800,             # 连接回收时间（秒），防止数据库端断开
    pool_pre_ping=True,            # 使用前 ping 测试连接是否有效
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    """用户表模型"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100))

async def get_db():
    """数据库会话依赖"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ========== 2. Redis 缓存配置 ==========
redis_client = Redis.from_url("redis://localhost:6379/0", decode_responses=True)

# ========== 3. 本地缓存（函数级）==========
@lru_cache(maxsize=128)
def expensive_computation(n: int) -> int:
    """模拟耗时计算，结果被本地缓存"""
    time.sleep(0.1)  # 模拟计算（注意：这是同步的，仅作示例）
    return n * n

# ========== 4. 缓存装饰器（Redis 分布式缓存）==========
def cache_with_redis(expire: int = 60):
    """
    Redis 缓存装饰器（简化版）
    - expire: 缓存过期时间（秒）
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 构建缓存 key
            cache_key = f"cache:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存读取
            cached = await redis_client.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
            
            # 执行原函数
            result = await func(*args, **kwargs)
            
            # 写入缓存
            import json
            await redis_client.setex(cache_key, expire, json.dumps(result, default=str))
            return result
        return wrapper
    return decorator

# ========== 路由 ==========
@app.get("/users/{user_id}")
@cache_with_redis(expire=120)  # 缓存2分钟
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """
    获取用户信息（带 Redis 缓存）
    - 先查缓存，缓存未命中再查数据库
    """
    # 模拟数据库查询
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        return {"error": "用户不存在"}
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "cached": False  # 装饰器会覆盖为 True
    }

@app.post("/users")
async def create_user(username: str, email: str, db: AsyncSession = Depends(get_db)):
    """创建用户（写操作需要清除相关缓存）"""
    new_user = User(username=username, email=email)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # 清除用户列表缓存（缓存失效策略）
    await redis_client.delete("cache:get_users:*")
    
    return {"id": new_user.id, "username": username}

# ========== 性能测试辅助 ==========
@app.get("/benchmark")
async def benchmark():
    """并发请求测试接口"""
    # 模拟多个异步 IO 操作并发执行
    async def fetch_data(i: int):
        await asyncio.sleep(0.01)  # 模拟 IO 等待
        return f"data_{i}"
    
    # 并发执行 100 个任务
    results = await asyncio.gather(*[fetch_data(i) for i in range(100)])
    return {"completed": len(results)}
```

### 常见面试题

**Q1：为什么要在异步应用中使用连接池？连接池的关键参数有哪些？**

> 数据库连接的创建涉及 TCP 三次握手、TLS 协商、数据库认证等步骤，通常需要 50-200ms，在高并发下频繁创建销毁会导致严重的性能瓶颈和端口耗尽。连接池通过复用已有连接将这一开销降低到接近零。关键参数包括：`pool_size`（基础连接数，根据并发量设置）、`max_overflow`（峰值容忍量）、`pool_timeout`（等待可用连接的超时，防止无限堆积）、`pool_recycle`（连接最大存活时间，防止数据库端超时断开导致的"僵尸连接"）、`pool_pre_ping`（使用前检测连接有效性）。合理配置后，连接池可以将数据库查询的 P99 延迟降低 30% 以上。

**Q2：如何解决缓存穿透、缓存击穿和缓存雪崩？**

> ① **缓存穿透**：查询一个数据库中也不存在的数据，导致每次请求都打到数据库。解决方案：**布隆过滤器**（Bloom Filter）预先拦截不存在的 key；对查询结果为空的也进行缓存（设置较短 TTL，如 60 秒）；接口层增加参数校验和限流。② **缓存击穿**：某个热点 key 过期瞬间，大量并发请求同时打到数据库。解决方案：使用**互斥锁**（如 Redis `SETNX`），保证只有一个线程去加载数据；或者设置热点 key **永不过期**，通过后台异步更新。③ **缓存雪崩**：大量 key 同时过期，导致数据库压力骤增。解决方案：给 TTL 添加**随机偏移量**（如 `expire = base + random(0, 300)`）；使用多级缓存（本地 + 分布式）；设置**熔断降级**机制，数据库压力过大时直接返回默认值或错误提示。

---

## 11. 测试（TestClient、依赖注入 mock）

测试是保障代码质量的核心环节。FastAPI 基于 Starlette 的 `TestClient` 提供了强大的同步测试能力，同时通过依赖覆盖（`dependency_overrides`）机制让 Mock 测试变得异常简单。

**TestClient**：`fastapi.testclient.TestClient` 基于 `httpx` 的同步客户端实现，可以在不启动服务器的情况下测试 FastAPI 应用。它处理 ASGI 应用的调用、请求构建和响应解析，支持 GET/POST/PUT/DELETE 等所有 HTTP 方法，以及表单提交、文件上传、Cookie/Header 操作。重要特性：`TestClient` 是**同步**的（基于 `anyio` 在内部运行异步代码），这意味着测试函数不需要 `async`/`await`。

**依赖注入 Mock**：FastAPI 的 `app.dependency_overrides` 字典允许在测试中将任意依赖替换为 Mock 实现。这是 FastAPI 测试的最大便利之处——无需复杂的数据库回滚或事务管理，只需替换 `get_db` 为返回内存数据库或 Mock 对象的函数即可。

**pytest + fixtures**：结合 `pytest` 的 fixture 机制，可以优雅地管理测试资源的生命周期：`app` fixture 创建应用实例，`client` fixture 创建 TestClient，`db` fixture 提供隔离的数据库会话。`autouse=True` 的 fixture 可以自动执行 setup/teardown。

**异步测试**：如果需要测试异步函数（如 WebSocket、Celery 任务），可以使用 `pytest-asyncio` 插件，配合 `async` 测试函数和 `async with AsyncClient`。

```python
# tests/test_main.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, select

# ========== 被测试的应用代码（假设在同一项目中）==========
from main import app, get_db, User, Base

# ========== 测试数据库配置（内存 SQLite）==========
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    """Mock 数据库依赖：使用内存数据库"""
    async with TestSessionLocal() as session:
        yield session

# 覆盖应用的数据库依赖
app.dependency_overrides[get_db] = override_get_db

# ========== pytest fixtures ==========
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """测试会话级别：创建和销毁测试数据库表"""
    import asyncio
    asyncio.run(_create_tables())
    yield
    asyncio.run(_drop_tables())

async def _create_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def _drop_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session():
    """每个测试用例的独立数据库会话"""
    async with TestSessionLocal() as session:
        yield session
        # 回滚事务，确保测试隔离
        await session.rollback()

@pytest.fixture
def client():
    """TestClient fixture"""
    with TestClient(app) as c:
        yield c

# ========== 测试用例 ==========
class TestUserAPI:
    """用户 API 测试类"""
    
    def test_create_user(self, client: TestClient):
        """测试创建用户"""
        response = client.post("/users", params={"username": "testuser", "email": "test@example.com"})
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert "id" in data
    
    def test_create_user_duplicate(self, client: TestClient):
        """测试重复创建用户"""
        # 第一次创建
        client.post("/users", params={"username": "dupuser", "email": "dup@example.com"})
        # 第二次创建（假设有唯一约束）
        response = client.post("/users", params={"username": "dupuser", "email": "dup2@example.com"})
        # 根据实际业务逻辑调整断言
        assert response.status_code in [200, 409, 400]
    
    def test_get_user(self, client: TestClient):
        """测试获取用户"""
        # 先创建用户
        create_resp = client.post("/users", params={"username": "getuser", "email": "get@example.com"})
        user_id = create_resp.json()["id"]
        
        # 再查询
        response = client.get(f"/users/{user_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "getuser"
    
    def test_get_user_not_found(self, client: TestClient):
        """测试获取不存在的用户"""
        response = client.get("/users/99999")
        assert response.status_code == 404
    
    def test_get_user_invalid_id(self, client: TestClient):
        """测试无效的用户ID（数据校验）"""
        response = client.get("/users/abc")
        assert response.status_code == 422  # FastAPI 自动返回校验错误
        data = response.json()
        assert "detail" in data

# ========== Mock 外部服务的测试示例 ==========
class MockEmailService:
    """Mock 邮件服务"""
    sent_emails = []
    
    @staticmethod
    async def send_email(to: str, subject: str, body: str):
        MockEmailService.sent_emails.append({"to": to, "subject": subject})
        return True

async def mock_send_email(to: str, subject: str, body: str):
    """邮件服务依赖的 Mock 实现"""
    return await MockEmailService.send_email(to, subject, body)

# 假设应用中有 email_service 依赖，可以这样覆盖：
# app.dependency_overrides[email_service] = mock_send_email

# ========== 运行测试 ==========
# pytest tests/ -v --tb=short
# pytest tests/test_main.py::TestUserAPI::test_create_user -v
```

### 常见面试题

**Q1：FastAPI 的 `TestClient` 是同步的，如何测试异步代码？**

> `TestClient` 内部使用 `anyio` 在同步上下文中运行异步的 ASGI 应用，因此对测试代码而言调用方式是同步的（`client.get()` 而非 `await client.get()`）。这种方式的优势是测试代码更简单，无需 `pytest-asyncio` 等额外插件即可覆盖 90% 的测试场景。如果需要测试纯异步函数（如独立的异步工具函数、Celery 任务、WebSocket），可以使用 `pytest-asyncio` 插件编写 `async def` 测试函数，并使用 `async with AsyncClient(app=app, base_url="http://test") as ac:` 进行异步 HTTP 测试。两种模式可以共存于同一个测试套件中。

**Q2：如何在测试中隔离数据库状态，避免测试互相影响？**

> 最佳实践是**每个测试用例使用独立的事务**：① 在 fixture 中创建数据库会话，测试结束后执行 `rollback()`，不提交任何更改；② 使用内存数据库（如 `sqlite:///:memory:`）作为测试数据库，速度快且完全隔离；③ 对于集成测试需要真实数据库时，使用 `pytest` 的 `function` 级别 fixture，每个测试函数前后清理数据；④ 利用 FastAPI 的 `dependency_overrides` 将 `get_db` 替换为返回测试会话的函数。避免在生产数据库上运行测试，也避免使用 `DELETE FROM table` 清理数据（慢且容易遗漏关联表）。

---

## 12. 部署（Gunicorn + Uvicorn、Docker、ASGI 原理）

将 FastAPI 应用部署到生产环境涉及服务器选择、进程管理、容器化和性能调优等多个层面。理解 ASGI 协议和服务器架构是做出正确部署决策的基础。

**ASGI 协议**：ASGI（Asynchronous Server Gateway Interface）是 Python 的异步 Web 服务器网关接口标准，是 WSGI 的继任者。ASGI 应用是一个异步可调用对象，接收 `scope`（连接信息）、`receive`（接收消息通道）、`send`（发送消息通道）三个参数。FastAPI 应用本质上就是一个 ASGI 应用。ASGI 支持 HTTP、WebSocket、Lifespan 等多种协议，而 WSGI 仅支持同步 HTTP。

**Uvicorn**：基于 `uvloop`（Cython 实现的高速事件循环）和 `httptools`（C 实现的 HTTP 解析器）的 ASGI 服务器，是运行 FastAPI 的首选。Uvicorn 可以单进程运行（开发环境：`uvicorn main:app --reload`），也可以作为 worker 被 Gunicorn 管理（生产环境）。

**Gunicorn + Uvicorn Worker**：Gunicorn 是成熟的 Python WSGI HTTP 服务器，擅长进程管理（自动重启失效 worker、平滑升级、信号处理），但它本身不支持 ASGI。通过 `uvicorn.workers.UvicornWorker` 类，Gunicorn 可以管理多个 Uvicorn 进程，每个进程运行独立的 ASGI 应用实例。这种模式结合了 Gunicorn 的运维能力和 Uvicorn 的异步性能。生产环境的典型命令：`gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000`。

**Docker 部署**：Docker 化部署的标准做法是基于官方 Python 镜像，安装依赖，暴露端口，使用 Gunicorn 启动。生产 Dockerfile 应遵循最佳实践：使用非 root 用户、多阶段构建减小镜像体积、设置合理的 `PYTHONDONTWRITEBYTECODE` 和 `PYTHONUNBUFFERED` 环境变量、配置健康检查。

```python
# main.py - 应用入口
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello, Production!"}

@app.get("/health")
async def health():
    return {"status": "ok"}
```

```dockerfile
# Dockerfile - 生产环境
FROM python:3.11-slim as builder

# 构建依赖
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# 生产镜像
FROM python:3.11-slim

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# 安装运行时依赖
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

# 非 root 用户运行（安全最佳实践）
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 使用 Gunicorn + Uvicorn Worker 启动
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
```

```yaml
# docker-compose.yml - 本地/测试环境
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/app
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: app
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

```bash
#!/bin/bash
# deploy.sh - 部署脚本示例

# 构建镜像
docker build -t myapp:latest .

# 运行容器（生产环境）
docker run -d \
  --name myapp \
  --restart always \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql://..." \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  -e WORKERS=4 \
  myapp:latest

# 或者使用 docker-compose
docker-compose -f docker-compose.prod.yml up -d
```

**Worker 数量调优**：Gunicorn 的 worker 数量通常设置为 `2 * CPU核心数 + 1`。这个公式源自经验法则，确保在 CPU 密集和 I/O 密集混合负载下有较好的利用率。如果应用主要是 I/O 密集型（如大量数据库/网络调用），可以适当增加 worker 数量；如果是 CPU 密集型，worker 数量不应超过 CPU 核心数，否则会导致上下文切换开销。

**反向代理**：生产环境中，Gunicorn 前面通常放置 Nginx 作为反向代理。Nginx 处理静态文件、SSL 终止、负载均衡、速率限制，将动态请求转发给 Gunicorn。这种分层架构提升了安全性和性能。

### 常见面试题

**Q1：为什么不直接用 Uvicorn 生产部署，而需要 Gunicorn + Uvicorn Worker？**

> Uvicorn 是单进程服务器，不具备进程管理功能。直接使用 Uvicorn 生产部署存在以下问题：① **无 worker 管理**：单个进程崩溃会导致整个服务中断，Gunicorn 可以自动重启失效 worker；② **无法平滑升级**：代码更新时需要手动重启，Gunicorn 支持 `HUP` 信号实现零停机重载；③ **信号处理不完善**：Gunicorn 对 `SIGTERM`/`SIGINT` 的处理更完善，支持优雅关闭；④ **缺少运维特性**：如 worker 超时自动重启、最大请求数限制（防止内存泄漏）、统计和监控接口。最佳实践是：**Gunicorn 负责进程管理和运维，Uvicorn Worker 负责 ASGI 协议处理**，两者各司其职。

**Q2：ASGI 和 WSGI 的本质区别是什么？为什么 FastAPI 选择 ASGI？**

> **WSGI**（Web Server Gateway Interface）是 Python 的同步 Web 接口标准，基于函数调用模型（`application(environ, start_response)`），每个请求对应一个函数调用，请求处理期间线程被阻塞，无法处理并发。这导致高并发场景下需要大量线程/进程，内存开销巨大。**ASGI** 是异步接口标准，基于异步可调用对象（`await application(scope, receive, send)`），使用事件循环和协程处理并发，单线程即可支撑数千并发连接。ASGI 还支持 WebSocket、HTTP/2 Server Push、Lifespan 等现代 Web 协议。FastAPI 选择 ASGI 是因为：① 原生支持 `async`/`await`，充分利用 Python 的异步 IO；② 性能远超 WSGI 框架；③ 支持 WebSocket 等全双工通信；④ 与现代 Python 异步生态（asyncpg、aioredis、httpx）无缝集成。

---

> **本章小结**：FastAPI 凭借其异步架构、类型注解驱动的开发体验和现代化的设计哲学，已成为 Python 后端开发的首选框架之一。掌握其核心特性、依赖注入、认证授权、性能优化和部署实践，是应对后端面试的关键。建议读者结合官方文档和实际项目经验，深入理解每个知识点的底层原理。




---


# 第四章：后端/Web 基础

> 本章深入讲解 Web 后端开发的核心知识体系，从底层网络协议到高层架构设计，从安全防护到性能优化。掌握这些内容，是成为合格后端工程师的必经之路。

---

## 1. HTTP 协议详解

### 1.1 概述

HTTP（HyperText Transfer Protocol，超文本传输协议）是 Web 通信的基石，基于客户端-服务器架构，默认运行在 TCP 的 80 端口（HTTPS 为 443 端口）。HTTP/1.1 是目前最广泛使用的版本，而 HTTP/2 和 HTTP/3（基于 QUIC）正在逐步普及，它们通过多路复用和更高效的传输协议显著提升了性能。

HTTP 是一种**无状态协议**，即服务器不会记住之前请求的任何信息。这种设计简化了服务器实现，但也带来了会话管理的挑战——需要通过 Cookie、Session 等机制来模拟状态。

### 1.2 HTTP 方法

| 方法 | 幂等性 | 安全性 | 用途 |
|------|--------|--------|------|
| GET | 是 | 是 | 获取资源，参数在 URL 中，有长度限制 |
| POST | 否 | 否 | 创建资源，数据在请求体中，无长度限制 |
| PUT | 是 | 否 | 全量更新资源（替换整个资源） |
| PATCH | 否 | 否 | 局部更新资源（仅修改部分字段） |
| DELETE | 是 | 否 | 删除指定资源 |
| HEAD | 是 | 是 | 获取响应头，不返回响应体 |
| OPTIONS | 是 | 是 | 获取服务器支持的 HTTP 方法，用于 CORS 预检 |

> **幂等性**：多次执行相同操作，结果与执行一次相同。例如多次 GET 同一资源，结果一致。

### 1.3 HTTP 状态码

状态码分为五大类：

- **1xx 信息响应**：100 Continue（继续发送请求体）
- **2xx 成功**：200 OK、201 Created、204 No Content
- **3xx 重定向**：301 永久重定向、302 临时重定向、304 Not Modified
- **4xx 客户端错误**：400 Bad Request、401 未认证、403 禁止访问、404 未找到
- **5xx 服务器错误**：500 内部错误、502 Bad Gateway、503 服务不可用

### 1.4 HTTP 首部字段

```http
# 常见请求头
GET /api/users HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Encoding: gzip, deflate
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json
User-Agent: Mozilla/5.0...

# 常见响应头
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Content-Length: 256
Cache-Control: max-age=3600
Set-Cookie: session_id=xxx; HttpOnly; Secure
```

### 1.5 HTTP 缓存机制

HTTP 缓存是性能优化的关键手段，通过减少网络请求来提升页面加载速度。

**强缓存**（不发送请求到服务器）：
- `Cache-Control: max-age=3600`（HTTP/1.1，单位秒）
- `Expires: Wed, 21 Oct 2026 07:28:00 GMT`（HTTP/1.0，绝对时间）

**协商缓存**（发送请求到服务器验证）：
- `Last-Modified` + `If-Modified-Since`（基于时间，精度为秒）
- `ETag` + `If-None-Match`（基于内容哈希，更精确）

缓存优先级：`Cache-Control` > `Expires`；当强缓存过期后，浏览器会携带协商缓存字段向服务器验证。

### 1.6 Cookie 与 Session

**Cookie** 是服务器发送到客户端并保存在浏览器端的小型文本数据，后续请求会自动携带。

```python
# Flask 中设置 Cookie
from flask import Flask, make_response

app = Flask(__name__)

@app.route('/set-cookie')
def set_cookie():
    resp = make_response('Cookie 已设置')
    # max_age: 有效期（秒）；httponly: 禁止 JS 访问，防 XSS
    resp.set_cookie('user_id', '12345', max_age=3600, httponly=True, secure=True, samesite='Lax')
    return resp

# 读取 Cookie
@app.route('/get-cookie')
def get_cookie():
    user_id = request.cookies.get('user_id')
    return f'用户ID: {user_id}'
```

**Session** 是服务器端保存的用户会话数据，通常通过 Cookie 传递 Session ID 来关联。

```python
# Flask 中 Session 的使用（基于服务器端存储）
from flask import Flask, session

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # 用于签名 Session Cookie

@app.route('/login', methods=['POST'])
def login():
    # 验证用户名密码...
    session['user_id'] = '12345'
    session['username'] = '张三'
    return '登录成功'

@app.route('/profile')
def profile():
    user_id = session.get('user_id')
    if not user_id:
        return '未登录', 401
    return f'用户: {session["username"]}'

@app.route('/logout')
def logout():
    session.clear()  # 清除 Session
    return '已登出'
```

**Cookie vs Session 对比**：

| 特性 | Cookie | Session |
|------|--------|---------|
| 存储位置 | 客户端（浏览器） | 服务器端 |
| 安全性 | 较低，可被篡改 | 较高，数据不暴露 |
| 存储容量 | 约 4KB | 无限制（服务器内存或 Redis） |
| 性能影响 | 每次请求携带，增加带宽 | 需查服务器存储 |
| 适用场景 | 非敏感偏好设置 | 用户登录状态、敏感数据 |

### 常见面试题

#### Q1: HTTP/1.1 与 HTTP/2 的主要区别是什么？

**参考答案：**

1. **多路复用（Multiplexing）**：HTTP/1.1 中浏览器对同一域名通常只开 6-8 个 TCP 连接，且每个连接同一时间只能处理一个请求（队头阻塞）。HTTP/2 允许在单一 TCP 连接上并行传输多个请求和响应，通过二进制分帧层将数据切分为帧，带上流标识符后交错发送。

2. **头部压缩**：HTTP/2 使用 HPACK 算法压缩头部，减少冗余传输。静态表存储常见头字段，动态表维护会话中重复出现的头字段。

3. **服务器推送**：HTTP/2 允许服务器主动将资源推送到客户端缓存，例如请求 HTML 时，服务器可主动推送 CSS 和 JS 文件。

4. **二进制协议**：HTTP/1.1 是文本协议，HTTP/2 采用二进制格式，解析更高效。

#### Q2: 什么是 HTTP 的 keep-alive？它解决了什么问题？

**参考答案：**

HTTP/1.0 中每个请求/响应都需要建立新的 TCP 连接，建立 TCP 连接需要三次握手，加上 TLS 握手（HTTPS），开销很大。

HTTP/1.1 默认启用 `Connection: keep-alive`，允许复用同一个 TCP 连接发送多个请求和响应，避免了重复的握手开销。但 keep-alive 仍受队头阻塞（Head-of-Line Blocking）影响——一个请求阻塞会导致后续请求等待。

HTTP/2 的多路复用从根本上解决了这个问题，而 HTTP/3 基于 QUIC（UDP）彻底消除了 TCP 层队头阻塞。

---

## 2. TCP/IP 三次握手与四次挥手

### 2.1 TCP 协议概述

TCP（Transmission Control Protocol，传输控制协议）是一种**面向连接、可靠、基于字节流**的传输层协议。它在 IP 协议之上提供了以下核心能力：

- **可靠性**：通过序列号、确认应答（ACK）、超时重传保证数据不丢失
- **有序性**：通过序列号保证数据按发送顺序到达
- **流量控制**：通过滑动窗口机制防止发送方压垮接收方
- **拥塞控制**：通过慢启动、拥塞避免等算法防止网络拥塞

### 2.2 三次握手（建立连接）

三次握手是 TCP 建立连接的过程，目的是**同步双方的初始序列号，交换窗口大小，并确认双方的收发能力正常**。

```
客户端                                                服务器
   |                                                     |
   |  -------- SYN=1, seq=x -------->                    |  第一次握手：客户端请求建立连接，发送初始序列号 x
   |                                                     |
   |  <---- SYN=1, ACK=1, seq=y, ack=x+1 ----          |  第二次握手：服务器同意建立，发送自己的初始序列号 y，确认收到 x
   |                                                     |
   |  -------- ACK=1, seq=x+1, ack=y+1 -------->       |  第三次握手：客户端确认收到，连接建立
   |                                                     |
```

**为什么是三次而不是两次？**

两次握手的问题在于：如果客户端的第一个 SYN 报文在网络中延迟，客户端超时重发后成功建立连接并通信完毕释放了连接，此时延迟的 SYN 到达服务器，服务器会误以为是新的连接请求而响应。由于两次握手下客户端不会确认这个旧连接，服务器会一直等待，造成资源浪费。**三次握手通过客户端的最终确认，防止了历史重复连接的初始化。**

### 2.3 四次挥手（断开连接）

四次挥手是 TCP 连接终止的过程。由于 TCP 是全双工通信，双方需要分别关闭自己的发送通道。

```
客户端                                                服务器
   |                                                     |
   |  -------- FIN=1, seq=u -------->                    |  第一次挥手：客户端发送 FIN，表示不再发送数据
   |                                                     |
   |  <------------ ACK=1, ack=u+1 ------------          |  第二次挥手：服务器确认收到 FIN
   |                                                     |  （此时连接处于半关闭状态，服务器仍可发送数据）
   |  <-------- FIN=1, seq=w, ack=u+1 --------          |  第三次挥手：服务器也发送 FIN，表示不再发送数据
   |                                                     |
   |  ------------ ACK=1, ack=w+1 ------------>          |  第四次挥手：客户端确认，进入 TIME_WAIT 状态
   |                                                     |
```

**TIME_WAIT 状态的作用（持续 2MSL）：**

1. **保证最后一个 ACK 能被对方收到**：如果 ACK 丢失，服务器会重发 FIN，客户端在 TIME_WAIT 期间能重新响应。
2. **防止旧的连接数据包影响新连接**：等待网络中滞留的数据包全部消失，避免下一个使用相同四元组（源 IP、源端口、目的 IP、目的端口）的连接收到旧数据。

**为什么挥手是四次而握手是三次？**

因为握手时服务器的 SYN 和 ACK 可以同时发送（同意建立连接 + 自己的序列号），而挥手时服务器的 ACK 和 FIN 不能合并——收到客户端的 FIN 只意味着客户端不再发送数据，但服务器可能还有数据要发送，所以 ACK 和 FIN 必须分开发送。

### 2.4 Python 示例：使用 socket 观察 TCP 连接

```python
import socket
import threading

def tcp_server():
    """简单的 TCP 服务器，演示连接建立和断开"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 9999))
    server.listen(5)
    print("[服务器] 监听 127.0.0.1:9999")
    
    conn, addr = server.accept()
    print(f"[服务器] 接受连接来自 {addr}")
    
    # 接收数据
    data = conn.recv(1024)
    print(f"[服务器] 收到: {data.decode()}")
    
    # 发送响应后主动关闭
    conn.sendall(b'Hello from server')
    conn.close()
    print("[服务器] 连接已关闭")
    server.close()

def tcp_client():
    """TCP 客户端"""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("[客户端] 正在连接...")
    client.connect(('127.0.0.1', 9999))
    print("[客户端] 连接已建立")
    
    client.sendall(b'Hello from client')
    response = client.recv(1024)
    print(f"[客户端] 收到: {response.decode()}")
    
    client.close()
    print("[客户端] 连接已关闭")

if __name__ == '__main__':
    # 启动服务器线程
    t = threading.Thread(target=tcp_server)
    t.start()
    
    import time
    time.sleep(0.5)  # 等待服务器启动
    
    tcp_client()
    t.join()
```

### 常见面试题

#### Q1: 如果第三次握手失败了会怎样？

**参考答案：**

如果客户端发送的第三个 ACK 报文丢失：

1. **服务器端**：收不到 ACK，会重发第二次握手的 SYN+ACK 报文（通常重试 5 次，间隔时间指数增长）。如果最终仍未收到 ACK，服务器会释放资源，关闭半连接。

2. **客户端端**：认为自己已经发送了 ACK，连接已建立。如果此时发送数据，服务器会以 RST（复位）报文响应，客户端收到 RST 后就知道连接未建立成功。

如果客户端在第三次握手后、服务器收到 ACK 前发送数据，服务器处于 SYN_RCVD 状态，收到数据后会直接丢弃（因为连接尚未完全建立），或者回复 RST。

#### Q2: 大量 CLOSE_WAIT 状态的原因和解决方案？

**参考答案：**

**CLOSE_WAIT** 出现在被动关闭方：对方发送 FIN 后，我方已回复 ACK，但尚未发送自己的 FIN。大量 CLOSE_WAIT 说明我方应用程序没有主动关闭连接。

**常见原因**：
1. 代码中没有正确调用 `close()` 或 `shutdown()`
2. 业务逻辑中连接使用完后未释放
3. 异常处理分支遗漏了资源释放
4. 高并发下连接池配置不当

**解决方案**：
1. 使用 `with` 语句或 try-finally 确保连接关闭
2. 检查连接池的最大连接数和超时配置
3. 使用 `lsof -i:port` 或 `netstat -an | grep CLOSE_WAIT` 定位问题进程
4. 设置 TCP keepalive，让操作系统自动清理死连接

---

## 3. RESTful API 设计规范

### 3.1 什么是 REST

REST（Representational State Transfer，表述性状态转移）是由 Roy Fielding 提出的软件架构风格，核心思想是**将一切资源抽象为 URI，通过标准的 HTTP 方法对资源进行操作**。REST 不是一个协议或标准，而是一组设计约束和原则。

REST 的六大原则：

1. **客户端-服务器架构**：分离关注点，客户端负责展示，服务器负责数据存储
2. **无状态**：每个请求必须包含所有必要信息，服务器不保存客户端状态
3. **可缓存**：响应必须显式或隐式标记为可缓存或不可缓存
4. **统一接口**：使用统一的资源标识和操作方式
5. **分层系统**：客户端不需要知道是否直接连接到服务器
6. **按需代码（可选）**：服务器可以扩展客户端功能（如 JavaScript）

### 3.2 RESTful 设计规范

**资源命名**：使用名词复数形式，避免动词。

```
GET    /api/v1/users           # 获取用户列表
GET    /api/v1/users/123       # 获取 ID 为 123 的用户
POST   /api/v1/users           # 创建用户
PUT    /api/v1/users/123       # 全量更新用户 123
PATCH  /api/v1/users/123       # 局部更新用户 123
DELETE /api/v1/users/123       # 删除用户 123

# 嵌套资源
GET    /api/v1/users/123/orders    # 获取用户 123 的订单列表
POST   /api/v1/users/123/orders    # 为用户 123 创建订单
```

**状态码的正确使用**：
- `200 OK`：GET、PUT、PATCH、DELETE 成功
- `201 Created`：POST 创建资源成功（响应头中通常包含 `Location` 指向新资源）
- `204 No Content`：DELETE 成功或 PUT 更新成功但无返回体
- `400 Bad Request`：请求参数错误（如缺少必填字段、格式错误）
- `401 Unauthorized`：未提供认证信息
- `403 Forbidden`：认证通过但无权限
- `404 Not Found`：资源不存在
- `409 Conflict`：资源冲突（如重复创建）
- `422 Unprocessable Entity`：语义错误（如业务规则校验失败）

**分页设计**：

```json
// 请求: GET /api/v1/users?page=1&per_page=20&sort=-created_at
{
    "data": [
        {"id": 1, "name": "张三"},
        {"id": 2, "name": "李四"}
    ],
    "pagination": {
        "page": 1,
        "per_page": 20,
        "total": 150,
        "total_pages": 8,
        "has_next": true,
        "has_prev": false
    }
}
```

**过滤、排序、字段选择**：

```
GET /api/v1/products?category=electronics&price_min=100&price_max=500
GET /api/v1/products?sort=-price,-created_at
GET /api/v1/users/123?fields=id,name,email
```

### 3.3 Flask 实现 RESTful API

```python
from flask import Flask, jsonify, request, abort
from functools import wraps

app = Flask(__name__)

# 模拟数据库
users_db = {
    1: {"id": 1, "name": "张三", "email": "zhangsan@example.com", "age": 25},
    2: {"id": 2, "name": "李四", "email": "lisi@example.com", "age": 30}
}

# 统一的 JSON 响应格式
def api_response(data=None, message="success", code=200):
    response = jsonify({"code": code, "message": message, "data": data})
    response.status_code = code
    return response

def api_error(message, code=400):
    return api_response(data=None, message=message, code=code)

# GET /users - 获取用户列表
@app.route('/api/v1/users', methods=['GET'])
def get_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    user_list = list(users_db.values())
    total = len(user_list)
    
    # 分页
    start = (page - 1) * per_page
    end = start + per_page
    paginated = user_list[start:end]
    
    return api_response(data={
        "items": paginated,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total
        }
    })

# GET /users/<id> - 获取单个用户
@app.route('/api/v1/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = users_db.get(user_id)
    if not user:
        return api_error("用户不存在", 404)
    return api_response(data=user)

# POST /users - 创建用户
@app.route('/api/v1/users', methods=['POST'])
def create_user():
    data = request.get_json()
    if not data or 'name' not in data:
        return api_error("缺少必填字段: name", 400)
    
    new_id = max(users_db.keys(), default=0) + 1
    new_user = {
        "id": new_id,
        "name": data['name'],
        "email": data.get('email', ''),
        "age": data.get('age', 0)
    }
    users_db[new_id] = new_user
    
    response = api_response(data=new_user, message="创建成功", code=201)
    response.headers['Location'] = f'/api/v1/users/{new_id}'
    return response

# PUT /users/<id> - 全量更新
@app.route('/api/v1/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    if user_id not in users_db:
        return api_error("用户不存在", 404)
    
    data = request.get_json()
    # PUT 要求全量更新，所有字段必须提供
    required = ['name', 'email', 'age']
    for field in required:
        if field not in data:
            return api_error(f"PUT 操作缺少字段: {field}", 400)
    
    users_db[user_id].update({
        "name": data['name'],
        "email": data['email'],
        "age": data['age']
    })
    return api_response(data=users_db[user_id], message="更新成功")

# PATCH /users/<id> - 局部更新
@app.route('/api/v1/users/<int:user_id>', methods=['PATCH'])
def patch_user(user_id):
    if user_id not in users_db:
        return api_error("用户不存在", 404)
    
    data = request.get_json()
    for key in ['name', 'email', 'age']:
        if key in data:
            users_db[user_id][key] = data[key]
    return api_response(data=users_db[user_id], message="更新成功")

# DELETE /users/<id> - 删除用户
@app.route('/api/v1/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if user_id not in users_db:
        return api_error("用户不存在", 404)
    
    del users_db[user_id]
    return api_response(message="删除成功", code=204)

if __name__ == '__main__':
    app.run(debug=True)
```

### 常见面试题

#### Q1: REST 和 RPC 的区别是什么？什么时候选择哪个？

**参考答案：**

| 特性 | REST | RPC（如 gRPC） |
|------|------|---------------|
| 核心思想 | 面向资源（名词） | 面向操作（动词） |
| 协议 | HTTP/1.1 或 HTTP/2 | HTTP/2 |
| 数据格式 | JSON/XML | Protocol Buffers（二进制） |
| 可读性 | 高 | 低（需解码） |
| 性能 | 较低（文本传输） | 高（二进制 + 连接复用） |
| 浏览器支持 | 原生支持 | 需 gRPC-Web 代理 |
| 缓存 | 可充分利用 HTTP 缓存 | 较难实现 |

**选择建议**：
- 对外公开的 API、浏览器端调用 → REST
- 内部微服务通信、追求极致性能 → gRPC
- 也可以混合使用：对外 REST，内部 gRPC

#### Q2: 如何设计一个支持版本控制的 RESTful API？

**参考答案：**

常见三种方案：

1. **URL 路径中嵌入版本**（最常用）：
   ```
   /api/v1/users
   /api/v2/users
   ```
   优点：清晰、可缓存、易于路由。
   缺点：URL 变更可能导致资源链接失效。

2. **请求头中指定版本**：
   ```
   Accept: application/vnd.api+json;version=2
   ```
   优点：URL 不变，资源标识稳定。
   缺点：不够直观，需要文档说明，缓存配置复杂。

3. **查询参数**：
   ```
   /api/users?api-version=2
   ```
   优点：简单。
   缺点：不符合 REST 资源定位思想，缓存困难。

**推荐做法**：URL 路径版本化 + 合理的弃用策略（Deprecated Header + 文档通知 + 过渡期）。

---

## 4. Web 安全

### 4.1 CSRF（跨站请求伪造）

CSRF 攻击利用用户已认证的会话，诱导用户在不知情的情况下执行非预期的操作。例如：用户登录了银行网站，然后访问了恶意网站，恶意网站中的表单自动向银行网站发起转账请求，由于浏览器会自动携带银行域的 Cookie，请求会被认证通过。

**防御方案**：

```python
from flask import Flask, session, request, abort
import secrets

app = Flask(__name__)
app.secret_key = 'your-secret-key'

def generate_csrf_token():
    """生成 CSRF Token 并存入 Session"""
    token = secrets.token_urlsafe(32)
    session['csrf_token'] = token
    return token

def validate_csrf_token():
    """验证 CSRF Token"""
    # 从请求头中获取 Token（优先）或表单数据
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token or token != session.get('csrf_token'):
        abort(403, 'CSRF token 验证失败')

# 在模板中嵌入 Token
@app.route('/transfer-form')
def transfer_form():
    token = generate_csrf_token()
    return f'''
    <form action="/transfer" method="POST">
        <input type="hidden" name="csrf_token" value="{token}">
        <input type="text" name="to_account" placeholder="收款账号">
        <input type="number" name="amount" placeholder="金额">
        <button type="submit">转账</button>
    </form>
    '''

# 处理转账请求前验证 CSRF Token
@app.route('/transfer', methods=['POST'])
def transfer():
    validate_csrf_token()
    # 执行转账逻辑...
    return '转账成功'
```

**其他防御手段**：
- **SameSite Cookie**：设置 `SameSite=Lax` 或 `SameSite=Strict`，阻止跨站请求携带 Cookie
- **验证 Origin/Referer 头**：检查请求来源是否合法
- **双重 Cookie 验证**：将 Token 同时存入 Cookie 和请求参数中，验证两者是否匹配

### 4.2 XSS（跨站脚本攻击）

XSS 攻击通过在网页中注入恶意脚本，使其在用户的浏览器中执行。分为三种类型：

1. **反射型 XSS**：恶意脚本通过 URL 参数传入，服务器直接回显到页面中
2. **存储型 XSS**：恶意脚本被存储到数据库，所有查看该页面的用户都会执行
3. **DOM 型 XSS**：通过修改页面 DOM 结构触发，不经过服务器

```python
from markupsafe import escape

@app.route('/search')
def search():
    # 危险：未转义的输出会导致 XSS
    # query = request.args.get('q', '')
    # return f'<p>搜索结果: {query}</p>'  # 如果 q=<script>alert('xss')</script> 就会执行
    
    # 安全：使用 escape 转义 HTML 特殊字符
    query = request.args.get('q', '')
    safe_query = escape(query)
    return f'<p>搜索结果: {safe_query}</p>'  # < 变成 &lt;，> 变成 &gt;
```

**防御策略**：
- 对所有用户输入进行 HTML 转义输出
- 使用 Content Security Policy（CSP）响应头限制脚本来源
- 对 Cookie 设置 `HttpOnly` 属性，防止 JavaScript 读取
- 使用现代框架（如 React、Vue）的自动转义机制

### 4.3 SQL 注入

SQL 注入通过在输入中嵌入 SQL 代码，操纵数据库执行非预期操作。

```python
import sqlite3

# ❌ 危险：字符串拼接 SQL
def unsafe_login(username, password):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # 如果 username 输入 ' OR '1'='1' --，密码验证被绕过
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)
    return cursor.fetchone()

# ✅ 安全：使用参数化查询
def safe_login(username, password):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # 参数化查询会自动转义特殊字符
    cursor.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, password)
    )
    return cursor.fetchone()

# ✅ SQLAlchemy ORM 方式（自动参数化）
from sqlalchemy.orm import Session
from models import User  # 假设有 ORM 模型

def orm_login(db: Session, username: str, password: str):
    return db.query(User).filter(
        User.username == username,
        User.password == password  # 实际应使用哈希比对
    ).first()
```

### 4.4 CORS（跨域资源共享）

浏览器的**同源策略**（Same-Origin Policy）限制了从一个源加载的文档或脚本如何与另一个源的资源交互。两个 URL 同源要求**协议、域名、端口**三者完全相同。

CORS 通过 HTTP 头部让服务器声明哪些源可以访问其资源：

```python
from flask import Flask, make_response
from functools import wraps

app = Flask(__name__)

def allow_cors(origins=None, methods=None, headers=None, credentials=False):
    """CORS 装饰器"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            resp = make_response(f(*args, **kwargs))
            
            origin = request.headers.get('Origin', '')
            allowed_origins = origins or ['http://localhost:3000']
            
            if origin in allowed_origins or '*' in allowed_origins:
                resp.headers['Access-Control-Allow-Origin'] = origin
            
            resp.headers['Access-Control-Allow-Methods'] = ', '.join(methods or ['GET', 'POST'])
            resp.headers['Access-Control-Allow-Headers'] = ', '.join(headers or ['Content-Type', 'Authorization'])
            
            if credentials:
                resp.headers['Access-Control-Allow-Credentials'] = 'true'
            
            return resp
        return wrapper
    return decorator

@app.route('/api/data', methods=['GET', 'OPTIONS'])
@allow_cors(origins=['https://app.example.com'], methods=['GET', 'POST'], credentials=True)
def get_data():
    if request.method == 'OPTIONS':
        # 预检请求（Preflight）处理
        return ''
    return {'data': 'sensitive info'}
```

> ⚠️ 生产环境中使用 `flask-cors` 等成熟库，不要手写 CORS 逻辑。

### 4.5 JWT 安全

JWT（JSON Web Token）用于无状态认证，但使用不当会带来安全风险：

```python
import jwt
import datetime
from functools import wraps

SECRET_KEY = 'your-256-bit-secret'  # 生产环境使用强随机密钥
ALGORITHM = 'HS256'

def generate_token(user_id: str, expires_hours: int = 2):
    """生成 JWT Token"""
    payload = {
        'sub': user_id,                           # 主题（用户标识）
        'iat': datetime.datetime.utcnow(),        # 签发时间
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=expires_hours),
        'jti': secrets.token_urlsafe(16)          # JWT ID，用于 Token 黑名单
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    """验证 JWT Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token 已过期
    except jwt.InvalidTokenError:
        return None  # Token 无效

# 作为装饰器保护路由
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'error': '缺少认证信息'}, 401
        
        token = auth_header.split(' ')[1]
        payload = verify_token(token)
        if not payload:
            return {'error': 'Token 无效或已过期'}, 401
        
        # 将用户信息存入请求上下文
        request.current_user = payload['sub']
        return f(*args, **kwargs)
    return wrapper
```

**JWT 安全最佳实践**：
1. **使用 HTTPS**：防止 Token 被中间人窃取
2. **设置合理的过期时间**：Access Token 短（15-60 分钟），Refresh Token 较长
3. **不要在 JWT 中存储敏感信息**：Payload 只是 Base64 编码，未加密
4. **密钥管理**：定期轮换密钥，使用非对称算法（RS256）便于多服务验证
5. **实现 Token 黑名单**：登出时将 Token 加入 Redis 黑名单，验证时检查

### 常见面试题

#### Q1: CSRF 和 XSS 的区别是什么？能否同时防御？

**参考答案：**

| 特性 | CSRF | XSS |
|------|------|-----|
| 攻击目标 | 利用用户已认证的会话执行操作 | 在受害者浏览器中执行恶意脚本 |
| 信任关系 | 利用网站对用户的信任 | 利用用户对网站的信任 |
| 是否需要用户交互 | 需要（点击链接或访问页面） | 可能不需要（存储型 XSS 自动触发） |
| 能否读取响应 | 不能（受同源策略限制） | 能（脚本在同源执行） |

可以同时防御：
- CSRF Token 防御 CSRF，CSP 和输出转义防御 XSS
- `SameSite=Strict` Cookie 同时减轻两种风险
- 但两者攻击向量不同，没有单一的银弹方案

#### Q2: 如何安全地实现用户密码存储？

**参考答案：**

绝对不要明文存储或简单哈希（MD5/SHA1）密码。

正确做法：
1. 使用**专门的密码哈希算法**：bcrypt、Argon2 或 scrypt
2. **加盐（Salt）**：每个密码使用独立随机盐值，防止彩虹表攻击
3. **调整计算成本**：设置适当的 work factor（如 bcrypt 的 rounds=12），使哈希计算耗时 100ms 以上

```python
import bcrypt

def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希"""
    # bcrypt 自动生成盐值并嵌入结果中
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# 使用示例
hashed = hash_password('user_password')
print(verify_password('user_password', hashed))  # True
print(verify_password('wrong_password', hashed))  # False
```

---

## 5. 异步编程基础

### 5.1 为什么需要异步编程

传统的同步编程中，当程序执行 I/O 操作（如网络请求、文件读写、数据库查询）时，线程会被阻塞，CPU 空转等待 I/O 完成。在高并发场景下，为每个请求创建一个线程/进程会导致：

- 大量内存消耗（每个线程栈 1-8MB）
- 线程上下文切换开销
- C10K 问题（无法高效处理上万并发连接）

**异步编程的核心思想**：当遇到 I/O 操作时，挂起当前任务，让出 CPU 去执行其他任务；当 I/O 完成后，恢复之前的任务继续执行。这样单个线程就能高效处理大量并发。

### 5.2 async/await 语法

Python 3.5+ 引入 `async` 和 `await` 关键字，让异步代码看起来像同步代码：

```python
import asyncio
import aiohttp
import time

# async def 定义协程函数
async def fetch_url(session: aiohttp.ClientSession, url: str):
    """异步获取单个 URL"""
    print(f"[开始] 请求 {url}")
    async with session.get(url) as response:  # await 挂起，等待网络响应
        data = await response.text()          # 再次挂起，等待数据读取完成
        print(f"[完成] {url} - 长度: {len(data)}")
        return len(data)

async def fetch_all():
    """并发获取多个 URL"""
    urls = [
        'https://httpbin.org/delay/1',
        'https://httpbin.org/delay/1',
        'https://httpbin.org/delay/1',
    ]
    
    async with aiohttp.ClientSession() as session:
        # asyncio.gather 并发执行多个协程
        results = await asyncio.gather(
            *[fetch_url(session, url) for url in urls]
        )
        return results

# 运行事件循环
if __name__ == '__main__':
    start = time.time()
    results = asyncio.run(fetch_all())  # Python 3.7+ 推荐方式
    print(f"总耗时: {time.time() - start:.2f}秒, 结果: {results}")
    # 并发请求 3 个延迟 1 秒的接口，总耗时约 1 秒而非 3 秒
```

**关键规则**：
- `await` 只能在 `async def` 函数中使用
- `await` 后面必须是**可等待对象**（Awaitable）：协程、任务（Task）、Future
- 在普通函数中调用协程，需要使用 `asyncio.run()` 或 `loop.run_until_complete()`

### 5.3 事件循环

事件循环（Event Loop）是异步编程的核心调度器，它维护一个任务队列，不断执行以下循环：

1. 从队列中取出一个就绪任务
2. 执行任务直到遇到 `await`
3. 将任务挂起，注册 I/O 回调
4. 当 I/O 完成时，任务重新标记为就绪
5. 重复步骤 1

```python
import asyncio

async def task(name, delay):
    print(f"任务 {name} 开始")
    await asyncio.sleep(delay)  # sleep 是模拟 I/O 的协程
    print(f"任务 {name} 完成")

async def main():
    # 创建任务（Task）会立即调度到事件循环
    t1 = asyncio.create_task(task("A", 2))
    t2 = asyncio.create_task(task("B", 1))
    t3 = asyncio.create_task(task("C", 3))
    
    # 等待所有任务完成
    await asyncio.gather(t1, t2, t3)
    
    # 获取任务结果（如果协程有返回值）
    # result = await t1

# 手动管理事件循环（不推荐，仅用于理解）
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(main())
finally:
    loop.close()
```

### 5.4 协程、任务、Future

| 概念 | 说明 |
|------|------|
| **Coroutine（协程）** | `async def` 定义的函数，调用时返回协程对象，不会立即执行 |
| **Task（任务）** | 对协程的包装，调度到事件循环中执行，可取消、可获取结果 |
| **Future** | 低级别的可等待对象，代表一个异步操作的未来结果 |

```python
async def demo():
    # 协程对象 - 尚未执行
    coro = asyncio.sleep(1)
    print(type(coro))  # <class 'coroutine'>
    
    # 包装为 Task - 已调度到事件循环
    task = asyncio.create_task(asyncio.sleep(1))
    print(type(task))  # <class '_asyncio.Task'>
    
    # Future - 低级别操作
    future = asyncio.get_event_loop().create_future()
    future.set_result('done')
    print(await future)  # 'done'
```

### 5.5 异步编程实战：并发爬虫

```python
import asyncio
import aiohttp
from aiohttp import ClientTimeout
import json

class AsyncCrawler:
    """异步并发爬虫，支持限流和错误处理"""
    
    def __init__(self, max_concurrent=10, timeout=30):
        self.semaphore = asyncio.Semaphore(max_concurrent)  # 信号量限制并发数
        self.timeout = ClientTimeout(total=timeout)
    
    async def fetch(self, session: aiohttp.ClientSession, url: str) -> dict:
        """获取单个 URL，受信号量控制并发"""
        async with self.semaphore:  # 获取信号量许可
            try:
                async with session.get(url, timeout=self.timeout) as resp:
                    text = await resp.text()
                    return {
                        'url': url,
                        'status': resp.status,
                        'length': len(text),
                        'error': None
                    }
            except asyncio.TimeoutError:
                return {'url': url, 'status': None, 'length': 0, 'error': 'timeout'}
            except Exception as e:
                return {'url': url, 'status': None, 'length': 0, 'error': str(e)}
    
    async def crawl(self, urls: list[str]) -> list[dict]:
        """并发爬取多个 URL"""
        connector = aiohttp.TCPConnector(limit=100)  # 连接池限制
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self.fetch(session, url) for url in urls]
            return await asyncio.gather(*tasks, return_exceptions=True)

# 使用示例
async def main():
    crawler = AsyncCrawler(max_concurrent=5)
    urls = [f'https://httpbin.org/get?i={i}' for i in range(20)]
    results = await crawler.crawl(urls)
    
    success = sum(1 for r in results if r.get('error') is None)
    print(f"成功: {success}/{len(urls)}")
    print(json.dumps(results[:3], indent=2, ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
```

### 常见面试题

#### Q1: `asyncio.gather` 和 `asyncio.wait` 的区别？

**参考答案：**

- **`asyncio.gather(*aws)`**：
  - 并发执行所有可等待对象
  - 返回结果列表，与输入顺序一致
  - 默认第一个异常会取消其他未完成任务（`return_exceptions=True` 可改变）
  - 适用于需要收集所有结果的场景

- **`asyncio.wait(aws)`**：
  - 更底层，返回 `(done, pending)` 两个任务集合
  - 可配置 `return_when`（FIRST_COMPLETED、FIRST_EXCEPTION、ALL_COMPLETED）
  - 适用于需要精细化控制的任务管理（如超时后取消剩余任务）

```python
# gather 用法
results = await asyncio.gather(task1, task2, task3, return_exceptions=True)

# wait 用法
done, pending = await asyncio.wait(
    [task1, task2, task3],
    return_when=asyncio.FIRST_COMPLETED
)
for task in pending:
    task.cancel()
```

#### Q2: 如何在异步代码中调用同步阻塞函数？

**参考答案：**

使用 `asyncio.to_thread()`（Python 3.9+）或 `loop.run_in_executor()` 在线程池中执行同步代码，避免阻塞事件循环：

```python
import asyncio
import time

def sync_blocking_task(n):
    """模拟耗时的同步操作（如 CPU 密集型计算）"""
    time.sleep(n)  # 同步 sleep 会阻塞线程
    return f"阻塞任务完成，耗时 {n} 秒"

async def main():
    # 方法1: asyncio.to_thread (Python 3.9+)
    result = await asyncio.to_thread(sync_blocking_task, 2)
    print(result)
    
    # 方法2: run_in_executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sync_blocking_task, 2)
    print(result)
    
    # 方法3: 使用自定义线程池
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = await loop.run_in_executor(pool, sync_blocking_task, 2)
        print(result)

asyncio.run(main())
```

---

## 6. WSGI vs ASGI

### 6.1 WSGI（Web Server Gateway Interface）

WSGI 是 Python Web 应用程序与 Web 服务器之间的标准接口（PEP 3333），定义于 2003 年。它是同步接口，每个请求由一个独立的线程或进程处理。

```python
# 最简单的 WSGI 应用（符合 WSGI 规范的可调用对象）
def simple_wsgi_app(environ, start_response):
    """
    environ: 包含所有请求信息的字典（请求方法、路径、头、查询参数等）
    start_response: 回调函数，用于设置状态码和响应头
    """
    status = '200 OK'
    headers = [('Content-Type', 'text/plain; charset=utf-8')]
    start_response(status, headers)
    
    # 返回可迭代对象作为响应体
    return [b'Hello, WSGI!']

# 使用标准库 wsgiref 运行
from wsgiref.simple_server import make_server

if __name__ == '__main__':
    server = make_server('localhost', 8000, simple_wsgi_app)
    print("WSGI 服务器运行在 http://localhost:8000")
    server.serve_forever()
```

**WSGI 的特点**：
- 同步接口，不支持 WebSocket、HTTP/2 Server Push
- 成熟的生态系统：Gunicorn、uWSGI、mod_wsgi 等生产级服务器
- 框架支持：Flask、Django（传统模式）、Bottle 等

### 6.2 ASGI（Asynchronous Server Gateway Interface）

ASGI 是 WSGI 的继任者（于 2016 年提出），专为异步 Python 设计。它支持 HTTP、WebSocket、HTTP/2 等协议，允许单个应用内处理长连接和实时通信。

```python
# 最简单的 ASGI 应用
async def simple_asgi_app(scope, receive, send):
    """
    scope: 连接信息字典（类型、路径、头等）
    receive: 异步函数，接收客户端消息
    send: 异步函数，发送响应给客户端
    """
    # 处理 HTTP 请求
    if scope['type'] == 'http':
        # 接收请求体（如果有）
        # message = await receive()
        
        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'content-type', b'text/plain; charset=utf-8']]
        })
        await send({
            'type': 'http.response.body',
            'body': b'Hello, ASGI!'
        })
    
    # 处理 WebSocket 连接
    elif scope['type'] == 'websocket':
        await send({'type': 'websocket.accept'})
        message = await receive()
        if message['type'] == 'websocket.receive':
            await send({
                'type': 'websocket.send',
                'text': f"Echo: {message.get('text', '')}"
            })
        await send({'type': 'websocket.close'})

# 使用 uvicorn 运行
# uvicorn app:simple_asgi_app --host 0.0.0.0 --port 8000
```

### 6.3 WSGI vs ASGI 对比

| 特性 | WSGI | ASGI |
|------|------|------|
| 同步/异步 | 同步 | 异步（也可兼容同步） |
| 协议支持 | HTTP/1.x | HTTP/1.x、HTTP/2、WebSocket |
| 长连接 | 不支持 | 原生支持 |
| 并发模型 | 多线程/多进程 | 单线程事件循环 + 协程 |
| 生产服务器 | Gunicorn、uWSGI | Uvicorn、Hypercorn、Daphne |
| 框架 | Flask、Django（传统） | FastAPI、Starlette、Django（3.1+ 异步） |
| 性能 | 中等 | 高（I/O 密集型场景） |
| 生态成熟度 | 非常成熟 | 快速发展中 |

### 6.4 框架演进

```python
# Flask（WSGI） - 简洁但同步
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello Flask'

# FastAPI（ASGI） - 现代、异步、自动文档
from fastapi import FastAPI
import asyncio

app = FastAPI()

@app.get('/')
async def hello():
    await asyncio.sleep(0.1)  # 模拟异步 I/O
    return {'message': 'Hello FastAPI'}

@app.get('/users/{user_id}')
async def get_user(user_id: int):
    """路径参数自动校验和类型转换"""
    return {'user_id': user_id}

# 运行: uvicorn main:app --reload
# 自动文档: http://localhost:8000/docs
```

### 常见面试题

#### Q1: 为什么 WSGI 不能支持 WebSocket？

**参考答案：**

WSGI 的设计基于**请求-响应模型**：应用接收一个请求，处理后返回一个响应，连接即关闭。这种模型有以下限制：

1. **接口签名限制**：`app(environ, start_response)` 只能返回一次响应体，无法持续双向通信
2. **同步阻塞**：WSGI 服务器为每个请求分配独立线程/进程，长连接会占用大量资源
3. **无状态推送**：WebSocket 需要服务器主动向客户端推送消息，但 WSGI 中 `start_response` 只能调用一次

ASGI 通过三个参数解决了这些问题：`scope`（连接元信息）、`receive`（持续接收消息）、`send`（持续发送消息），使得长连接和双向通信成为可能。

---

## 7. 设计模式在 Web 开发中的应用

### 7.1 工厂模式（Factory Pattern）

工厂模式将对象的创建逻辑封装起来，使代码不直接依赖具体类，而依赖抽象接口。在 Web 开发中常用于数据库连接、日志记录器、外部服务客户端的创建。

```python
from abc import ABC, abstractmethod
from typing import Dict, Type

# 抽象产品
class PaymentGateway(ABC):
    @abstractmethod
    def charge(self, amount: float, currency: str) -> dict:
        pass
    
    @abstractmethod
    def refund(self, transaction_id: str) -> dict:
        pass

# 具体产品
class AlipayGateway(PaymentGateway):
    def charge(self, amount: float, currency: str) -> dict:
        return {'gateway': 'Alipay', 'amount': amount, 'status': 'success'}
    
    def refund(self, transaction_id: str) -> dict:
        return {'gateway': 'Alipay', 'transaction_id': transaction_id, 'status': 'refunded'}

class WechatGateway(PaymentGateway):
    def charge(self, amount: float, currency: str) -> dict:
        return {'gateway': 'Wechat', 'amount': amount, 'status': 'success'}
    
    def refund(self, transaction_id: str) -> dict:
        return {'gateway': 'Wechat', 'transaction_id': transaction_id, 'status': 'refunded'}

# 工厂
class PaymentGatewayFactory:
    _gateways: Dict[str, Type[PaymentGateway]] = {
        'alipay': AlipayGateway,
        'wechat': WechatGateway,
    }
    
    @classmethod
    def create(cls, gateway_type: str) -> PaymentGateway:
        if gateway_type not in cls._gateways:
            raise ValueError(f"不支持的支付方式: {gateway_type}")
        return cls._gateways[gateway_type]()
    
    @classmethod
    def register(cls, name: str, gateway_class: Type[PaymentGateway]):
        """注册新的支付方式（开闭原则）"""
        cls._gateways[name] = gateway_class

# 使用
class PaymentService:
    def process_payment(self, gateway_type: str, amount: float):
        gateway = PaymentGatewayFactory.create(gateway_type)
        return gateway.charge(amount, 'CNY')

# 测试
service = PaymentService()
print(service.process_payment('alipay', 100.0))
print(service.process_payment('wechat', 200.0))
```

### 7.2 单例模式（Singleton Pattern）

确保一个类只有一个实例，并提供一个全局访问点。在 Web 开发中常用于数据库连接池、配置管理、缓存客户端。

```python
import threading
from typing import Optional

class DatabaseConnectionPool:
    """线程安全的单例连接池"""
    
    _instance: Optional['DatabaseConnectionPool'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                # 双重检查锁定（Double-Checked Locking）
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_connections: int = 10):
        # 防止重复初始化
        if self._initialized:
            return
        
        self.max_connections = max_connections
        self._pool = []
        self._semaphore = threading.Semaphore(max_connections)
        self._initialized = True
        print(f"[连接池] 初始化完成，最大连接数: {max_connections}")
    
    def get_connection(self):
        self._semaphore.acquire()
        # 简化示例，实际应从池中获取真实连接
        conn_id = len(self._pool)
        self._pool.append(conn_id)
        print(f"[连接池] 获取连接 #{conn_id}")
        return conn_id
    
    def release_connection(self, conn_id):
        if conn_id in self._pool:
            self._pool.remove(conn_id)
        self._semaphore.release()
        print(f"[连接池] 释放连接 #{conn_id}")

# 测试单例
pool1 = DatabaseConnectionPool(max_connections=5)
pool2 = DatabaseConnectionPool(max_connections=100)  # 不会覆盖之前的配置
print(pool1 is pool2)  # True

conn = pool1.get_connection()
pool1.release_connection(conn)
```

**Python 中的更简洁实现**（使用模块导入机制）：

```python
# config.py - 模块天然是单例
class AppConfig:
    def __init__(self):
        self.debug = False
        self.database_url = 'postgresql://localhost/db'
        self.secret_key = 'default-secret'
    
    def load_from_env(self):
        import os
        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
        self.database_url = os.getenv('DATABASE_URL', self.database_url)

# 全局单例实例
config = AppConfig()

# 其他模块使用
# from config import config
# print(config.database_url)
```

### 7.3 策略模式（Strategy Pattern）

定义一系列算法，将它们封装起来，并且使它们可以互相替换。策略模式让算法的变化独立于使用算法的客户。

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

@dataclass
class Order:
    """订单"""
    id: str
    total: float
    items: List[dict]

# 策略接口
class DiscountStrategy(ABC):
    @abstractmethod
    def calculate_discount(self, order: Order) -> float:
        """返回折扣金额"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        pass

# 具体策略
class NoDiscount(DiscountStrategy):
    def calculate_discount(self, order: Order) -> float:
        return 0
    
    def get_name(self):
        return '无折扣'

class PercentageDiscount(DiscountStrategy):
    def __init__(self, percentage: float):
        self.percentage = percentage
    
    def calculate_discount(self, order: Order) -> float:
        return order.total * self.percentage
    
    def get_name(self):
        return f'{self.percentage*100:.0f}% 折扣'

class FixedAmountDiscount(DiscountStrategy):
    def __init__(self, amount: float):
        self.amount = amount
    
    def calculate_discount(self, order: Order) -> float:
        return min(self.amount, order.total)  # 折扣不超过订单金额
    
    def get_name(self):
        return f'满减 {self.amount} 元'

class MemberDiscount(DiscountStrategy):
    def __init__(self, member_level: str):
        self.discounts = {'silver': 0.05, 'gold': 0.10, 'platinum': 0.15}
        self.level = member_level
    
    def calculate_discount(self, order: Order) -> float:
        rate = self.discounts.get(self.level, 0)
        return order.total * rate
    
    def get_name(self):
        return f'{self.level} 会员折扣'

# 上下文
class PricingService:
    def __init__(self, strategy: DiscountStrategy = None):
        self._strategy = strategy or NoDiscount()
    
    def set_strategy(self, strategy: DiscountStrategy):
        """动态切换策略"""
        self._strategy = strategy
    
    def calculate_final_price(self, order: Order) -> dict:
        discount = self._strategy.calculate_discount(order)
        return {
            'original': order.total,
            'discount_name': self._strategy.get_name(),
            'discount_amount': round(discount, 2),
            'final': round(order.total - discount, 2)
        }

# 使用示例
order = Order(id='ORD-001', total=1000.0, items=[{'name': '商品A', 'price': 1000}])

service = PricingService()
print(service.calculate_final_price(order))

# 切换为会员折扣
service.set_strategy(MemberDiscount('gold'))
print(service.calculate_final_price(order))

# 切换为满减
service.set_strategy(FixedAmountDiscount(200))
print(service.calculate_final_price(order))
```

### 7.4 依赖注入（Dependency Injection）

依赖注入是一种实现控制反转（IoC）的方式，将对象的依赖从内部创建改为外部传入，降低模块耦合度。

```python
from abc import ABC, abstractmethod

# 抽象依赖
class MessageSender(ABC):
    @abstractmethod
    def send(self, to: str, content: str) -> bool:
        pass

class SMSSender(MessageSender):
    def send(self, to: str, content: str) -> bool:
        print(f"[短信] 发送到 {to}: {content}")
        return True

class EmailSender(MessageSender):
    def send(self, to: str, content: str) -> bool:
        print(f"[邮件] 发送到 {to}: {content}")
        return True

class PushSender(MessageSender):
    def send(self, to: str, content: str) -> bool:
        print(f"[推送] 发送到 {to}: {content}")
        return True

# 通过构造函数注入依赖
class NotificationService:
    def __init__(self, sender: MessageSender):
        self._sender = sender  # 依赖从外部传入
    
    def notify(self, user_id: str, message: str):
        return self._sender.send(user_id, message)

# 使用 - 可以轻松替换发送方式，无需修改 NotificationService
sms_service = NotificationService(SMSSender())
sms_service.notify('13800138000', '您的订单已发货')

email_service = NotificationService(EmailSender())
email_service.notify('user@example.com', '欢迎注册')

# 结合工厂模式，根据配置注入
class NotificationFactory:
    @staticmethod
    def create(channel: str) -> NotificationService:
        senders = {
            'sms': SMSSender,
            'email': EmailSender,
            'push': PushSender
        }
        sender_class = senders.get(channel, SMSSender)
        return NotificationService(sender_class())

# FastAPI 原生支持依赖注入
from fastapi import Depends, FastAPI

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Header(...)):
    return verify_token(token)

@app.get('/orders')
def list_orders(
    db: Session = Depends(get_db),           # 注入数据库会话
    user: User = Depends(get_current_user)   # 注入当前用户
):
    return db.query(Order).filter(Order.user_id == user.id).all()
```

### 常见面试题

#### Q1: 单例模式有哪些实现方式？Python 中哪种最好？

**参考答案：**

单例模式的常见实现方式：

1. **双重检查锁定**（线程安全，上面示例中使用）
2. **模块导入**（Python 推荐，利用模块只加载一次的特性）
3. **装饰器**：
   ```python
   def singleton(cls):
       instances = {}
       def wrapper(*args, **kwargs):
           if cls not in instances:
               instances[cls] = cls(*args, **kwargs)
           return instances[cls]
       return wrapper
   ```
4. **元类**：
   ```python
   class SingletonMeta(type):
       _instances = {}
       def __call__(cls, *args, **kwargs):
           if cls not in cls._instances:
               cls._instances[cls] = super().__call__(*args, **kwargs)
           return cls._instances[cls]
   ```

**Python 中最推荐的方式是模块级单例**：简单、线程安全、无需额外代码。因为 Python 的模块在首次导入时执行且缓存于 `sys.modules`，天然保证唯一实例。

---

## 8. 缓存策略

### 8.1 缓存层次

Web 应用中的缓存通常分为多个层次，从快到慢依次为：

1. **浏览器缓存**（最快，毫秒级）：通过 HTTP 缓存头控制
2. **CDN 缓存**：分发节点缓存静态资源
3. **反向代理缓存**（Nginx、Varnish）：缓存完整响应
4. **应用本地缓存**（进程内字典、LRU Cache）：函数结果、配置数据
5. **分布式缓存**（Redis、Memcached）：跨进程共享数据
6. **数据库缓存**：查询缓存、连接池

### 8.2 本地缓存

```python
from functools import lru_cache
from datetime import datetime, timedelta
import threading

# 方法1: functools.lru_cache - 适合纯函数
@lru_cache(maxsize=128)
def fibonacci(n: int) -> int:
    """斐波那契数列，使用 LRU 缓存避免重复计算"""
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# 方法2: 带 TTL 的本地缓存（线程安全）
class TTLCache:
    """支持过期时间的本地缓存"""
    
    def __init__(self, default_ttl: int = 300):
        self._cache = {}
        self._ttl = default_ttl
        self._lock = threading.RLock()
    
    def get(self, key: str):
        with self._lock:
            if key not in self._cache:
                return None
            
            value, expire_at = self._cache[key]
            if datetime.now() > expire_at:
                del self._cache[key]
                return None
            return value
    
    def set(self, key: str, value, ttl: int = None):
        with self._lock:
            expire = datetime.now() + timedelta(seconds=ttl or self._ttl)
            self._cache[key] = (value, expire)
    
    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

# 使用示例
cache = TTLCache(default_ttl=60)

def get_user_from_db(user_id: int):
    """模拟数据库查询"""
    print(f"[DB] 查询用户 {user_id}")
    return {"id": user_id, "name": f"用户{user_id}"}

def get_user(user_id: int):
    """带缓存的用户查询"""
    key = f"user:{user_id}"
    user = cache.get(key)
    if user is None:
        user = get_user_from_db(user_id)
        cache.set(key, user, ttl=300)
    return user

# 测试
print(get_user(1))  # 查数据库
print(get_user(1))  # 命中缓存
```

### 8.3 分布式缓存（Redis）

```python
import redis
import json
import pickle
from functools import wraps

class RedisCache:
    """Redis 分布式缓存封装"""
    
    def __init__(self, host='localhost', port=6379, db=0):
        self._redis = redis.Redis(
            host=host, port=port, db=db,
            decode_responses=False,  # 使用二进制序列化
            socket_connect_timeout=5,
            socket_timeout=5,
            max_connections=50       # 连接池大小
        )
    
    def get(self, key: str):
        data = self._redis.get(key)
        if data is None:
            return None
        return pickle.loads(data)
    
    def set(self, key: str, value, ttl: int = 300):
        serialized = pickle.dumps(value)
        self._redis.setex(key, ttl, serialized)
    
    def delete(self, key: str):
        self._redis.delete(key)
    
    def delete_pattern(self, pattern: str):
        """按模式删除（慎用，生产环境使用 SCAN）"""
        for key in self._redis.scan_iter(pattern):
            self._redis.delete(key)

# 缓存装饰器
def cached(cache: RedisCache, ttl: int = 300, key_prefix: str = ""):
    """自动缓存函数返回值的装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 构建缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{args}:{sorted(kwargs.items())}"
            
            # 尝试读取缓存
            result = cache.get(cache_key)
            if result is not None:
                print(f"[缓存命中] {cache_key}")
                return result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            print(f"[缓存写入] {cache_key}")
            return result
        return wrapper
    return decorator

# 使用示例
redis_cache = RedisCache()

@cached(redis_cache, ttl=60, key_prefix="product")
def get_product_detail(product_id: int):
    """获取商品详情"""
    print(f"[业务] 查询商品 {product_id}")
    return {"id": product_id, "name": f"商品{product_id}", "price": 99.9}

# 测试
print(get_product_detail(100))
print(get_product_detail(100))  # 命中缓存
```

### 8.4 缓存问题与解决方案

**缓存穿透**：查询一个**一定不存在**的数据，缓存不命中，请求直达数据库。

- **解决方案**：布隆过滤器预过滤；缓存空值（设置较短 TTL）

```python
class CachePenetrationGuard:
    """防止缓存穿透"""
    
    def __init__(self, cache: RedisCache):
        self.cache = cache
        self._null_placeholder = "__NULL__"
        self._null_ttl = 60  # 空值缓存时间短
    
    def get(self, key: str, loader_func):
        value = self.cache.get(key)
        if value == self._null_placeholder:
            return None  # 已知不存在，直接返回
        if value is not None:
            return value
        
        # 加载数据
        value = loader_func()
        if value is None:
            self.cache.set(key, self._null_placeholder, self._null_ttl)
        else:
            self.cache.set(key, value, 300)
        return value
```

**缓存击穿**：一个**热点 key 过期**的瞬间，大量并发请求同时到达数据库。

- **解决方案**：互斥锁（只允许一个线程回源）；逻辑过期（不设置 TTL，通过逻辑时间判断是否刷新）

```python
import threading

class CacheBreakdownGuard:
    """防止缓存击穿 - 互斥锁方案"""
    
    def __init__(self, cache: RedisCache):
        self.cache = cache
        self._locks = {}
        self._main_lock = threading.Lock()
    
    def get(self, key: str, loader_func, ttl: int = 300):
        value = self.cache.get(key)
        if value is not None:
            return value
        
        # 获取或创建锁
        with self._main_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
        
        # 只有一个线程能执行加载
        with self._locks[key]:
            # 双重检查
            value = self.cache.get(key)
            if value is not None:
                return value
            
            value = loader_func()
            if value is not None:
                self.cache.set(key, value, ttl)
            return value
```

**缓存雪崩**：**大量 key 同时过期**，或 Redis 宕机，导致请求洪峰涌向数据库。

- **解决方案**：过期时间加随机偏移；多级缓存（本地 + 分布式）；Redis 高可用（主从 + 哨兵/集群）；熔断降级

```python
import random

def set_with_random_ttl(cache, key, value, base_ttl: int = 300):
    """设置随机过期时间，避免同时失效"""
    jitter = random.randint(0, 60)  # 0-60 秒随机偏移
    cache.set(key, value, base_ttl + jitter)
```

### 常见面试题

#### Q1: 如何保证缓存与数据库的一致性？

**参考答案：**

缓存与数据库的一致性问题是分布式系统的经典难题，不存在完美的方案，常见策略：

1. **Cache-Aside（旁路缓存，最常用）**：
   - 读：先查缓存 → 未命中查数据库 → 写入缓存
   - 写：先更新数据库 → 再删除缓存（不是更新缓存）
   - 为什么是删除而不是更新缓存？因为并发场景下更新缓存可能导致脏数据。删除缓存简单且安全，下次读取时自然回源。

2. **Write-Through**：同时更新数据库和缓存（同步或异步），一致性最好但性能差。

3. **Write-Behind**：先写缓存，异步批量写数据库，性能最好但可能丢数据。

**缓存删除失败的应对**：
- 使用消息队列（MQ）进行异步补偿重试
- 设置缓存的较短 TTL，最终一致性

---

## 9. 消息队列基础

### 9.1 消息队列的作用

消息队列（MQ）是分布式系统中实现异步通信、解耦服务、削峰填谷的核心组件：

1. **异步处理**：用户请求不需要等待耗时操作完成（如发送邮件、生成报表）
2. **应用解耦**：生产者不需要知道消费者是谁，各自独立演进
3. **流量削峰**：高并发时将请求暂存队列，系统按处理能力消费
4. **数据分发**：一条消息可被多个消费者处理
5. **最终一致性**：通过消息保证分布式事务的最终一致性

### 9.2 RabbitMQ 核心概念

RabbitMQ 是一个实现了 AMQP 协议的开源消息代理，核心概念：

- **Exchange（交换机）**：接收生产者消息，根据路由规则转发到 Queue
- **Queue（队列）**：存储消息的缓冲区
- **Binding（绑定）**：Exchange 和 Queue 之间的关联规则
- **Routing Key（路由键）**：消息携带的路由标识

Exchange 类型：

| 类型 | 说明 | 场景 |
|------|------|------|
| **Direct** | 精确匹配 Routing Key | 点对点任务分发 |
| **Fanout** | 广播到所有绑定队列 | 消息广播 |
| **Topic** | 模式匹配（`*` 匹配一个单词，`#` 匹配多个） | 日志分类、事件订阅 |
| **Headers** | 根据消息头属性匹配 | 复杂路由规则 |

```python
import pika
import json

class RabbitMQClient:
    """RabbitMQ 客户端封装"""
    
    def __init__(self, host='localhost', port=5672):
        self._params = pika.ConnectionParameters(host=host, port=port)
        self._connection = None
        self._channel = None
    
    def connect(self):
        self._connection = pika.BlockingConnection(self._params)
        self._channel = self._connection.channel()
    
    def declare_exchange(self, name: str, exchange_type: str = 'direct', durable: bool = True):
        self._channel.exchange_declare(exchange=name, exchange_type=exchange_type, durable=durable)
    
    def declare_queue(self, name: str, durable: bool = True):
        self._channel.queue_declare(queue=name, durable=durable)
    
    def bind_queue(self, queue: str, exchange: str, routing_key: str):
        self._channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
    
    def publish(self, exchange: str, routing_key: str, body: dict):
        """发送消息"""
        message = json.dumps(body, ensure_ascii=False)
        self._channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=message.encode('utf-8'),
            properties=pika.BasicProperties(
                delivery_mode=2,  # 消息持久化
                content_type='application/json'
            )
        )
    
    def consume(self, queue: str, callback, auto_ack: bool = False):
        """消费消息"""
        def wrapper(ch, method, properties, body):
            try:
                message = json.loads(body.decode('utf-8'))
                callback(message)
                ch.basic_ack(delivery_tag=method.delivery_tag)  # 手动确认
            except Exception as e:
                print(f"处理消息失败: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        
        # 公平分发：每次只取一条，处理完再取
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(queue=queue, on_message_callback=wrapper, auto_ack=auto_ack)
        print(f"开始消费队列: {queue}")
        self._channel.start_consuming()
    
    def close(self):
        if self._connection and not self._connection.is_closed:
            self._connection.close()

# 生产者示例
def send_order_created_event():
    client = RabbitMQClient()
    client.connect()
    client.declare_exchange('orders', 'topic')
    client.declare_queue('order_notifications')
    client.bind_queue('order_notifications', 'orders', 'order.created')
    
    client.publish('orders', 'order.created', {
        'order_id': 'ORD-20260813-001',
        'user_id': 'U123',
        'amount': 299.9,
        'status': 'created'
    })
    client.close()
    print("订单创建事件已发送")

# 消费者示例
def process_notification(message):
    print(f"[通知服务] 处理订单事件: {message}")
    # 发送邮件/短信通知...

def start_consumer():
    client = RabbitMQClient()
    client.connect()
    client.consume('order_notifications', process_notification)
```

### 9.3 Kafka 核心概念

Kafka 是分布式流处理平台，设计为高吞吐量、持久化的消息系统：

- **Topic（主题）**：消息的分类，逻辑上的消息队列
- **Partition（分区）**：Topic 的物理分片，每个分区是有序的日志序列
- **Offset（偏移量）**：消息在分区中的唯一标识，消费者通过 Offset 追踪消费位置
- **Producer（生产者）**：向 Topic 发布消息
- **Consumer Group（消费者组）**：组内消费者共同消费一个 Topic，分区分配给组内成员
- **Broker**：Kafka 服务器节点
- **Replication（副本）**：分区副本保证高可用

```python
from kafka import KafkaProducer, KafkaConsumer
import json

# Kafka 生产者
producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
    acks='all',           # 等待所有副本确认
    retries=3,            # 发送失败重试
    compression_type='gzip'  # 消息压缩
)

# 发送消息（指定 key 确保相同 key 进入同一分区，保证顺序）
future = producer.send(
    topic='user-events',
    key=b'user-123',      # 相同 key 进入同一分区
    value={'event': 'login', 'user_id': '123', 'timestamp': '2026-08-13T10:00:00Z'}
)
record_metadata = future.get(timeout=10)
print(f"消息已发送到分区 {record_metadata.partition}, offset {record_metadata.offset}")

producer.flush()
producer.close()

# Kafka 消费者（消费者组）
consumer = KafkaConsumer(
    'user-events',
    bootstrap_servers=['localhost:9092'],
    group_id='notification-service',  # 消费者组 ID
    auto_offset_reset='earliest',     # 无偏移时从最早开始
    enable_auto_commit=True,          # 自动提交偏移量
    auto_commit_interval_ms=5000,
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

for message in consumer:
    print(f"分区: {message.partition}, Offset: {message.offset}, 值: {message.value}")
    # 手动提交：consumer.commit_sync()

consumer.close()
```

### 9.4 RabbitMQ vs Kafka 对比

| 特性 | RabbitMQ | Kafka |
|------|----------|-------|
| 设计定位 | 通用消息代理 | 分布式流处理平台 |
| 消息模型 | 传统队列（消费后删除） | 持久化日志（消费后保留） |
| 吞吐量 | 万级/秒 | 百万级/秒 |
| 消息顺序 | 单队列内有序 | 分区内有序 |
| 消息回溯 | 不支持（消费即删除） | 支持（按 offset 重放） |
| 延迟 | 微秒级 | 毫秒级 |
| 适用场景 | 任务队列、RPC、实时通知 | 日志收集、流处理、事件溯源 |
| 消息确认 | 手动/自动 ACK | 按 offset 提交 |

### 常见面试题

#### Q1: 如何保证消息不丢失？

**参考答案：**

消息丢失可能发生在三个环节：

1. **生产者丢失**：
   - RabbitMQ：开启生产者确认（Publisher Confirm）
   - Kafka：设置 `acks=all`（所有副本确认才认为发送成功）

2. **消息队列丢失**：
   - RabbitMQ：队列和消息都设置 `durable=True`（持久化）
   - Kafka：分区配置多个副本（`replication.factor >= 3`）

3. **消费者丢失**：
   - RabbitMQ：关闭自动 ACK，业务处理成功后手动确认
   - Kafka：关闭自动提交偏移量，业务处理成功后手动 `commit_sync()`

```python
# RabbitMQ 生产者确认
channel.confirm_delivery()
try:
    channel.basic_publish(exchange='', routing_key='queue', body=body)
    print("消息已确认到达服务器")
except pika.exceptions.UnroutableError:
    print("消息可能被丢失，需要重试")

# Kafka 手动提交偏移量
for message in consumer:
    process(message.value)
    consumer.commit_sync()  # 处理成功后提交
```

---

## 10. 日志与监控

### 10.1 结构化日志

传统文本日志难以解析和分析。结构化日志以 JSON 等格式输出，便于机器处理和搜索。

```python
import logging
import json
import sys
from datetime import datetime
from pythonjsonlogger import jsonlogger  # pip install python-json-logger

# 自定义 JSON 格式化器
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['source'] = {
            'file': record.filename,
            'line': record.lineno,
            'function': record.funcName
        }

# 配置日志
def setup_logging():
    logger = logging.getLogger('app')
    logger.setLevel(logging.INFO)
    
    # 控制台输出 - 开发环境使用可读格式
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    
    # 文件输出 - 生产环境使用 JSON 格式
    file_handler = logging.FileHandler('app.log')
    file_handler.setFormatter(CustomJsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s'
    ))
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger

# 使用结构化日志
logger = setup_logging()

# 普通日志
logger.info("用户登录成功", extra={'user_id': '123', 'ip': '192.168.1.1'})

# 带上下文的日志
logger.warning("请求处理慢", extra={
    'request_id': 'req-abc-123',
    'path': '/api/orders',
    'duration_ms': 2500,
    'threshold_ms': 1000
})

# 错误日志（自动包含异常信息）
try:
    1 / 0
except Exception:
    logger.error("计算失败", extra={'operation': 'divide', 'dividend': 1, 'divisor': 0}, exc_info=True)
```

### 10.2 日志级别与规范

| 级别 | 用途 | 生产环境 |
|------|------|----------|
| DEBUG | 详细的调试信息，如变量值、执行路径 | 关闭 |
| INFO | 正常业务事件，如请求处理完成、用户操作 | 开启 |
| WARNING | 预期外的但可恢复的情况，如降级处理、重试 | 开启 |
| ERROR | 功能受损的错误，需要人工介入 | 开启，立即告警 |
| CRITICAL | 系统级故障，服务不可用 | 开启，立即告警 |

**日志规范**：
- 每条日志包含 `request_id`，用于串联同一次请求的所有日志
- 敏感信息（密码、Token）不脱敏不上日志
- 使用 `extra` 传递结构化字段，而不是字符串拼接
- 异常日志必须包含 `exc_info=True` 以保留堆栈

### 10.3 链路追踪（Distributed Tracing）

微服务架构中，一个请求可能经过多个服务。链路追踪通过唯一的 Trace ID 串联所有调用，帮助定位性能瓶颈和故障点。

```python
import uuid
import time
from contextvars import ContextVar
from typing import Optional
import logging

# 使用 ContextVar 存储请求上下文（线程/协程安全）
request_context: ContextVar[dict] = ContextVar('request_context', default={})

def get_current_context() -> dict:
    return request_context.get()

def get_trace_id() -> str:
    ctx = get_current_context()
    return ctx.get('trace_id', 'unknown')

def get_span_id() -> str:
    ctx = get_current_context()
    return ctx.get('span_id', 'unknown')

class TracedLogger:
    """自动注入 Trace ID 的日志记录器"""
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
    
    def _make_extra(self, extra: dict = None) -> dict:
        base = {
            'trace_id': get_trace_id(),
            'span_id': get_span_id()
        }
        if extra:
            base.update(extra)
        return base
    
    def info(self, msg: str, extra: dict = None):
        self._logger.info(msg, extra=self._make_extra(extra))
    
    def warning(self, msg: str, extra: dict = None):
        self._logger.warning(msg, extra=self._make_extra(extra))
    
    def error(self, msg: str, extra: dict = None, exc_info: bool = False):
        self._logger.error(msg, extra=self._make_extra(extra), exc_info=exc_info)

# 模拟 FastAPI 中间件中的链路追踪
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
logger = TracedLogger('api')

@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    """为每个请求创建 Trace ID 和 Span"""
    # 从请求头中获取上游传入的 Trace ID，或生成新的
    trace_id = request.headers.get('X-Trace-ID', str(uuid.uuid4()))
    span_id = str(uuid.uuid4())[:8]
    
    # 设置上下文
    token = request_context.set({
        'trace_id': trace_id,
        'span_id': span_id,
        'path': request.url.path,
        'method': request.method
    })
    
    start_time = time.time()
    logger.info("请求开始", extra={'path': request.url.path, 'method': request.method})
    
    try:
        response = await call_next(request)
        duration = (time.time() - start_time) * 1000
        
        logger.info("请求完成", extra={
            'status_code': response.status_code,
            'duration_ms': round(duration, 2)
        })
        
        response.headers['X-Trace-ID'] = trace_id
        return response
        
    except Exception as e:
        logger.error("请求异常", extra={'error': str(e)}, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "trace_id": trace_id}
        )
    finally:
        request_context.reset(token)

# 模拟服务间调用（传播 Trace ID）
import httpx

async def call_user_service(user_id: str):
    """调用用户服务，传递 Trace ID"""
    trace_id = get_trace_id()
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f'http://user-service/api/users/{user_id}',
            headers={'X-Trace-ID': trace_id}  # 传播 Trace ID
        )
        return response.json()

@app.get('/api/orders/{order_id}')
async def get_order(order_id: str):
    """获取订单详情（会调用用户服务）"""
    logger.info("查询订单", extra={'order_id': order_id})
    
    # 模拟调用下游服务
    user = await call_user_service('123')
    
    return {
        'order_id': order_id,
        'user': user,
        'trace_id': get_trace_id()
    }
```

### 10.4 监控指标

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# 定义指标
REQUEST_COUNT = Counter(
    'http_requests_total',
    'HTTP 请求总数',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP 请求处理时间（秒）',
    ['method', 'endpoint'],
    buckets=[.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0]
)

ACTIVE_REQUESTS = Gauge(
    'http_active_requests',
    '当前活跃请求数',
    ['method', 'endpoint']
)

# 在 FastAPI 中集成
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    from time import time
    
    path = request.url.path
    method = request.method
    
    ACTIVE_REQUESTS.labels(method=method, endpoint=path).inc()
    start = time()
    
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception:
        status = 500
        raise
    finally:
        duration = time() - start
        REQUEST_COUNT.labels(method=method, endpoint=path, status_code=status).inc()
        REQUEST_DURATION.labels(method=method, endpoint=path).observe(duration)
        ACTIVE_REQUESTS.labels(method=method, endpoint=path).dec()

# 暴露 Prometheus 指标端点
@app.get('/metrics')
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### 常见面试题

#### Q1: 日志中如何处理敏感信息？

**参考答案：**

1. **脱敏处理**：对手机号、身份证号、银行卡号等字段进行掩码
   ```python
   def mask_phone(phone: str) -> str:
       return phone[:3] + '****' + phone[-4:] if len(phone) >= 7 else phone
   ```

2. **配置化脱敏**：定义敏感字段列表，自动过滤
   ```python
   SENSITIVE_FIELDS = {'password', 'token', 'secret', 'credit_card'}
   
   def sanitize(data: dict) -> dict:
       return {k: '***' if k in SENSITIVE_FIELDS else v for k, v in data.items()}
   ```

3. **分级日志**：DEBUG 级别可记录详细参数（仅开发环境开启），生产环境只记录 INFO 及以上

4. **审计日志分离**：敏感操作的审计日志单独存储，与业务日志隔离，访问权限严格控制

---

> **本章完**。后端/Web 基础涵盖了从网络协议到架构设计的广泛知识。理解这些原理不仅有助于应对面试，更是构建高性能、高可用、安全的 Web 应用的基石。建议结合实际项目深入实践，特别关注异步编程、缓存策略和安全防护这三个在生产环境中影响最大的领域。




---


# 第 5 章：并发编程

并发编程是 Python 后端面试中的核心考点，也是日常开发中提升系统性能的关键手段。Python 提供了多线程、多进程和协程三种主要的并发模型，每种模型都有其独特的适用场景和底层原理。深入理解它们的工作机制、GIL 的影响以及线程安全问题，是每一位 Python 工程师的必修课。

---

## 1. GIL 详解与影响

### 概念解释

GIL（Global Interpreter Lock，全局解释器锁）是 CPython 解释器中的一个核心机制，它本质上是一把**互斥锁（Mutex）**，用于保护对 Python 对象内存管理的访问。在任何时刻，**同一进程中只有一个线程能持有 GIL 并执行 Python 字节码**。这意味着，尽管你的程序创建了多个线程，但在 CPython 层面，它们无法真正并行执行 Python 代码。

GIL 的存在主要是为了**简化 CPython 的内存管理**。Python 使用引用计数（Reference Counting）来管理内存回收，当对象的引用计数降为 0 时，解释器会立即回收该内存。如果没有 GIL，多个线程同时修改同一个对象的引用计数将导致竞争条件（Race Condition）和内存泄漏甚至崩溃。GIL 通过强制同一时刻只有一个线程执行，避免了在引用计数操作上加锁的复杂性和性能开销。

GIL 对不同类型的程序影响截然不同：

1. **纯 Python 计算密集型任务**：由于只有一个线程能执行字节码，多线程无法利用多核 CPU。此时，多线程不仅不能加速，反而因为线程上下文切换的开销，可能比单线程更慢。

2. **I/O 密集型任务**：当线程执行 I/O 操作（如网络请求、文件读写）时，它会释放 GIL，让其他线程获得执行机会。因此，多线程在 I/O 密集型场景下仍能提升效率。

3. **C 扩展计算密集型任务**：如果计算逻辑是在 C 扩展中完成的（如 NumPy、Pandas），且该扩展在执行期间主动释放 GIL，那么多线程仍然可以实现并行计算。

需要强调的是，**GIL 是 CPython 的特性，不是 Python 语言的特性**。Jython（基于 JVM）和 IronPython（基于 .NET）就没有 GIL。但在绝大多数生产环境中，我们使用的都是 CPython，因此必须正视 GIL 的存在。

### 代码示例

```python
"""
演示 GIL 对多线程计算密集型任务的影响。
对比单线程、多线程、多进程在执行 CPU 密集型任务时的性能差异。
"""

import threading
import multiprocessing
import time


def cpu_bound_task(n):
    """一个纯 Python 的 CPU 密集型任务：计算大量数的平方和。"""
    total = 0
    for i in range(n):
        total += i * i
    return total


def run_single_thread():
    """单线程顺序执行。"""
    start = time.perf_counter()
    cpu_bound_task(5_000_000)
    cpu_bound_task(5_000_000)
    end = time.perf_counter()
    print(f"单线程耗时: {end - start:.4f} 秒")


def run_multi_thread():
    """多线程执行——由于 GIL 存在，无法并行。"""
    start = time.perf_counter()
    t1 = threading.Thread(target=cpu_bound_task, args=(5_000_000,))
    t2 = threading.Thread(target=cpu_bound_task, args=(5_000_000,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    end = time.perf_counter()
    print(f"多线程耗时: {end - start:.4f} 秒")


def run_multi_process():
    """多进程执行——真正利用多核 CPU 并行计算。"""
    start = time.perf_counter()
    p1 = multiprocessing.Process(target=cpu_bound_task, args=(5_000_000,))
    p2 = multiprocessing.Process(target=cpu_bound_task, args=(5_000_000,))
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    end = time.perf_counter()
    print(f"多进程耗时: {end - start:.4f} 秒")


if __name__ == "__main__":
    print("=== GIL 影响对比测试 ===")
    run_single_thread()
    run_multi_thread()
    run_multi_process()
    # 预期结果：多线程耗时 ≈ 单线程，多进程耗时 ≈ 单线程的一半
```

### 常见面试题

#### 面试题 1：GIL 是什么？它为什么存在？如何规避它的影响？

**参考答案：**

GIL（Global Interpreter Lock）是 CPython 解释器中的一把全局锁，确保同一时刻只有一个线程在执行 Python 字节码。它存在的主要原因是简化内存管理——CPython 使用引用计数进行垃圾回收，GIL 避免了多线程同时修改引用计数带来的竞争条件。

规避 GIL 影响的常见方法有：

1. **使用多进程**：每个进程有独立的 Python 解释器和 GIL，可以真正实现并行计算。`multiprocessing` 模块是标准选择。
2. **使用 C 扩展**：如 NumPy、Pandas 等库，其底层 C 代码在执行计算时会释放 GIL，允许线程并行。
3. **使用替代解释器**：如 Jython、IronPython，或者使用 `Cython` 的 `nogil` 上下文。
4. **使用子解释器（Python 3.12+）**：PEP 554 引入的子解释器可以在同一进程中运行多个独立的解释器，每个都有自己的 GIL。

#### 面试题 2：GIL 会在 I/O 操作时释放吗？为什么多线程做网络请求还是有效的？

**参考答案：**

是的，GIL 在执行 I/O 操作时会释放。当线程调用阻塞式 I/O（如 `socket.read()`、`time.sleep()`）时，解释器会释放 GIL，让其他线程有机会执行。因此，多线程在处理 I/O 密集型任务（如网络爬虫、Web 服务）时仍然是有效的，因为线程在等待 I/O 期间不会阻塞整个程序的执行，其他线程可以充分利用这段时间处理其他请求。

---

## 2. 多线程（threading、线程池、线程同步）

### 概念解释

Python 的 `threading` 模块提供了对操作系统原生线程（POSIX threads / Windows threads）的封装。每个线程拥有独立的栈空间和程序计数器，但共享同一进程的内存空间（全局变量、堆内存等）。这种共享内存模型使得线程间通信非常高效，但也带来了**线程安全**的挑战。

创建线程有两种方式：
1. 直接实例化 `threading.Thread`，传入目标函数；
2. 继承 `threading.Thread` 并重写 `run()` 方法。

对于大量短生命周期任务，频繁创建和销毁线程开销较大，应使用**线程池**。`concurrent.futures.ThreadPoolExecutor` 是推荐的线程池实现（后文详述），而 `threading` 模块也提供了较底层的线程同步原语。

**线程同步**是多线程编程的核心课题。当多个线程访问共享数据时，必须使用同步机制来协调执行顺序，防止数据竞争（Data Race）。Python `threading` 模块提供了以下同步原语：

- **`Lock`（互斥锁）**：最基本的同步原语，同一时刻只有一个线程能获取锁。如果锁已被占用，其他线程会阻塞直到锁被释放。**不可重入**，同一线程重复获取会导致死锁。
- **`RLock`（可重入锁）**：允许同一线程多次获取同一个锁而不会阻塞自己。内部维护一个获取计数，只有计数归零时才会真正释放。适用于递归调用或嵌套函数中需要加锁的场景。
- **`Semaphore`（信号量）**：维护一个内部计数器，允许最多 N 个线程同时访问资源。常用于限制并发连接数、资源池大小等场景。`threading.Semaphore(1)` 退化为互斥锁。
- **`Condition`（条件变量）**：允许线程在满足特定条件之前等待，并在条件满足时被唤醒。通常与 Lock 配合使用，实现复杂的线程协作模式（如生产者-消费者模型）。
- **`Event`（事件）**：一个线程信号标志，所有线程可以等待它变为 True。适合用于线程间的简单通知。
- **`Barrier`（栅栏）**：等待指定数量的线程全部到达某点后，再同时放行。适合分阶段并行计算。

### 代码示例

```python
"""
多线程、线程池与线程同步原语的综合示例。
包含 Lock、RLock、Semaphore、Condition 的用法演示。
"""

import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor


# ============================================================
# 1. 基本线程创建与线程池
# ============================================================

def worker_task(name, duration):
    """模拟一个工作线程。"""
    print(f"[线程 {name}] 开始工作，预计耗时 {duration} 秒")
    time.sleep(duration)
    print(f"[线程 {name}] 工作完成")
    return f"{name} 的结果"


# 使用线程池执行批量任务
print("=== 线程池示例 ===")
with ThreadPoolExecutor(max_workers=3) as executor:
    # 提交多个任务
    futures = [executor.submit(worker_task, f"任务-{i}", random.uniform(0.5, 2))
               for i in range(5)]
    for future in futures:
        print(f"获取结果: {future.result()}")


# ============================================================
# 2. Lock 互斥锁——保护共享资源
# ============================================================

class BankAccount:
    """银行账户，演示 Lock 保护共享数据。"""

    def __init__(self, balance=0):
        self.balance = balance
        self._lock = threading.Lock()  # 每个账户一把锁

    def deposit(self, amount):
        """存款——使用锁保护余额修改。"""
        with self._lock:
            # 临界区开始
            new_balance = self.balance + amount
            time.sleep(0.001)  # 模拟 I/O 或复杂计算，放大竞争条件
            self.balance = new_balance
            # 临界区结束
        return self.balance

    def withdraw(self, amount):
        """取款——使用锁保护余额修改。"""
        with self._lock:
            if self.balance >= amount:
                new_balance = self.balance - amount
                time.sleep(0.001)
                self.balance = new_balance
                return True
            return False


def test_lock():
    account = BankAccount(balance=1000)

    def do_transactions():
        for _ in range(100):
            account.deposit(10)
            account.withdraw(10)

    threads = [threading.Thread(target=do_transactions) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"最终余额（应仍为 1000）: {account.balance}")


# ============================================================
# 3. RLock 可重入锁——递归或嵌套调用场景
# ============================================================

class RecursiveCounter:
    """演示 RLock：递归计数器，允许同一线程重入。"""

    def __init__(self):
        self.count = 0
        self._rlock = threading.RLock()

    def increment(self):
        with self._rlock:
            self.count += 1

    def recursive_increment(self, n):
        """递归调用，RLock 保证同一线程可以重入。"""
        if n <= 0:
            return
        with self._rlock:
            self.count += 1
            # 如果这里用普通 Lock，递归调用时会发生死锁！
            self.recursive_increment(n - 1)


# ============================================================
# 4. Semaphore 信号量——限制并发数量
# ============================================================

# 模拟数据库连接池，最多允许 2 个并发连接
connection_pool = threading.Semaphore(2)


def query_database(query_id):
    """模拟数据库查询，Semaphore 限制并发连接数。"""
    print(f"[查询 {query_id}] 请求连接...")
    with connection_pool:
        print(f"[查询 {query_id}] 获得连接，开始执行")
        time.sleep(1)  # 模拟查询耗时
        print(f"[查询 {query_id}] 释放连接")


# ============================================================
# 5. Condition 条件变量——生产者-消费者模型
# ============================================================

class BoundedBuffer:
    """有界缓冲区：经典的生产者-消费者问题。"""

    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = []
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)

    def put(self, item):
        """生产者放入物品。"""
        with self._not_full:
            # 如果缓冲区已满，等待消费者取走
            while len(self.buffer) >= self.capacity:
                print(f"[生产者] 缓冲区已满，等待...")
                self._not_full.wait()
            self.buffer.append(item)
            print(f"[生产者] 放入 {item}，当前: {self.buffer}")
            # 通知等待的消费者
            self._not_empty.notify()

    def get(self):
        """消费者取出物品。"""
        with self._not_empty:
            # 如果缓冲区为空，等待生产者放入
            while len(self.buffer) == 0:
                print(f"[消费者] 缓冲区为空，等待...")
                self._not_empty.wait()
            item = self.buffer.pop(0)
            print(f"[消费者] 取出 {item}，当前: {self.buffer}")
            # 通知等待的生产者
            self._not_full.notify()
            return item


def demo_condition():
    buffer = BoundedBuffer(capacity=3)

    def producer():
        for i in range(6):
            buffer.put(f"item-{i}")
            time.sleep(0.2)

    def consumer():
        for _ in range(6):
            buffer.get()
            time.sleep(0.5)

    t1 = threading.Thread(target=producer)
    t2 = threading.Thread(target=consumer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


if __name__ == "__main__":
    print("\n=== Lock 测试 ===")
    test_lock()

    print("\n=== Semaphore 测试 ===")
    for i in range(4):
        threading.Thread(target=query_database, args=(i,)).start()

    time.sleep(3)

    print("\n=== Condition 测试 ===")
    demo_condition()
```

### 常见面试题

#### 面试题 1：Lock 和 RLock 的区别是什么？什么时候应该用 RLock？

**参考答案：**

`Lock` 是普通互斥锁，同一线程如果重复获取会导致死锁；`RLock` 是可重入锁，同一线程可以多次获取，内部通过引用计数追踪嵌套层级，只有当获取次数等于释放次数时才会真正解锁。

应该使用 `RLock` 的场景包括：
- 递归函数中需要加锁；
- 类方法 A 获取锁后调用类方法 B，而 B 也需要获取同一把锁（嵌套调用）；
- 需要重入语义的任何场景。

在不需要重入的简单场景中，优先使用 `Lock`，因为它的开销更小、语义更简单。

#### 面试题 2：为什么用 `while` 而不是 `if` 来判断 Condition 的等待条件？

**参考答案：**

使用 `while` 是为了防止**虚假唤醒（Spurious Wakeup）**。`wait()` 被唤醒后，条件可能仍然不满足——原因包括：
1. 操作系统层面可能发生虚假唤醒（POSIX 线程规范允许这种情况）；
2. 多个消费者被同时唤醒（`notify_all`），但只有一个能获取到锁，当其他消费者最终获得锁时，条件可能已被前面的消费者改变。

如果用 `if`，线程被唤醒后会直接向下执行，可能导致在条件不满足时访问资源。`while` 确保线程在醒来后重新检查条件，只有条件真正满足时才继续执行，这是生产者-消费者模式的标准写法。

---

## 3. 多进程（multiprocessing、进程池、进程间通信）

### 概念解释

`multiprocessing` 模块是 Python 标准库中用于绕过 GIL、实现真正并行计算的核心工具。它通过创建多个独立的操作系统进程，每个进程拥有自己独立的 Python 解释器实例和 GIL，从而能够充分利用多核 CPU 的算力。

与多线程相比，多进程有以下特点：

- **真正的并行性**：由于每个进程独立运行，多进程可以同时在多个 CPU 核心上执行，适合 CPU 密集型任务。
- **内存隔离**：进程间内存不共享，一个进程的崩溃不会影响其他进程，提高了程序的稳定性。
- **更高的创建开销**：进程的创建比线程慢得多，因为它需要复制整个解释器状态。因此，对于大量短任务，应使用进程池来复用进程。
- **通信成本更高**：进程间不能简单共享内存，必须通过特定的 IPC（Inter-Process Communication）机制交换数据，序列化和反序列化带来额外开销。

**进程池（Pool）** 是管理大量计算任务的首选方式。`multiprocessing.Pool` 预先创建一组工作进程，将任务分发给它们执行，避免了频繁创建销毁进程的开销。常用方法包括 `apply()`（阻塞执行单任务）、`apply_async()`（非阻塞异步执行）、`map()`（批量映射）、`map_async()` 等。

**进程间通信（IPC）** 是多进程编程的核心挑战。`multiprocessing` 提供了多种 IPC 机制：

- **`Queue`**：基于管道和锁实现的进程安全队列，支持多个生产者和消费者，是最常用的 IPC 方式。底层通过 `pickle` 序列化数据。
- **`Pipe`**：双向或单向通信管道，返回一对连接对象 `(conn1, conn2)`。默认双向，可设置为单向。适合两个进程之间的点对点通信。
- **`SharedMemory`（Python 3.8+）**：`multiprocessing.shared_memory` 模块允许进程间共享同一块内存，避免了序列化开销，适合需要高效共享大型数组数据的场景（如 NumPy 数组）。
- **`Manager`**：提供一个服务器进程，其他进程通过代理对象访问共享数据（如 `Manager().list()`、`Manager().dict()`）。适合复杂数据结构，但速度较慢。
- **`Value` / `Array`**：共享的 ctypes 对象，存储在共享内存中，配合 `Lock` 使用可实现进程间的数值/数组共享。

### 代码示例

```python
"""
多进程、进程池与进程间通信（Queue、Pipe、SharedMemory）示例。
"""

import multiprocessing
import time
import os
from multiprocessing import Pool, Queue, Pipe, shared_memory
import array


# ============================================================
# 1. 进程池——批量处理 CPU 密集型任务
# ============================================================

def cpu_heavy(n):
    """CPU 密集型计算：判断一个数是否为素数。"""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True


def demo_pool():
    numbers = [11227253509529, 112582705942171, 115280095190773,
               115797848077099, 117450548693743]

    # 使用进程池并行判断素数
    with Pool(processes=os.cpu_count()) as pool:
        # map 会自动将任务分发给工作进程
        results = pool.map(cpu_heavy, numbers)
        for num, is_prime in zip(numbers, results):
            print(f"{num} 是素数: {is_prime}")


# ============================================================
# 2. Queue——进程间队列通信
# ============================================================

def producer(queue, items):
    """生产者进程：向队列中放入数据。"""
    pid = os.getpid()
    for item in items:
        print(f"[生产者 PID:{pid}] 放入: {item}")
        queue.put(item)
        time.sleep(0.1)
    # 发送结束信号
    queue.put(None)


def consumer(queue):
    """消费者进程：从队列中取出并处理数据。"""
    pid = os.getpid()
    while True:
        item = queue.get()
        if item is None:
            print(f"[消费者 PID:{pid}] 收到结束信号，退出")
            break
        print(f"[消费者 PID:{pid}] 处理: {item}")


def demo_queue():
    # Queue 会自动处理进程间的序列化和管道通信
    q = Queue(maxsize=10)
    items = ["数据-A", "数据-B", "数据-C", "数据-D", "数据-E"]

    p = multiprocessing.Process(target=producer, args=(q, items))
    c = multiprocessing.Process(target=consumer, args=(q,))

    p.start()
    c.start()
    p.join()
    c.join()


# ============================================================
# 3. Pipe——双向进程通信
# ============================================================

def pipe_worker(conn, name):
    """工作进程：通过 Pipe 接收任务，返回结果。"""
    while True:
        task = conn.recv()
        if task == "STOP":
            break
        # 模拟处理
        result = f"{name} 处理了 {task}"
        conn.send(result)


def demo_pipe():
    # Pipe() 返回两个连接对象，默认双向通信
    parent_conn, child_conn = Pipe()

    p = multiprocessing.Process(target=pipe_worker, args=(child_conn, "工作进程"))
    p.start()

    # 父进程发送任务
    for task in ["任务1", "任务2", "任务3"]:
        parent_conn.send(task)
        print(f"[主进程] 发送: {task}")
        result = parent_conn.recv()
        print(f"[主进程] 收到: {result}")

    parent_conn.send("STOP")
    p.join()


# ============================================================
# 4. SharedMemory——进程间共享内存（Python 3.8+）
# ============================================================

def shared_worker(shm_name, shape):
    """工作进程：访问共享内存并修改数据。"""
    # 通过名称附加到已存在的共享内存
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    # 将共享内存包装为数组
    arr = array.array('d', existing_shm.buf[:shape * 8])

    print(f"[工作进程] 读取共享数据: {list(arr)}")
    # 修改第一个元素
    with memoryview(existing_shm.buf) as mv:
        import struct
        mv[:8] = struct.pack('d', 999.9)
    print(f"[工作进程] 已修改共享数据")

    existing_shm.close()


def demo_shared_memory():
    # 创建 3 个 double 类型的共享内存（每个 8 字节）
    data = array.array('d', [1.1, 2.2, 3.3])
    shm = shared_memory.SharedMemory(create=True, size=data.buffer_info()[1] * 8)

    # 将初始数据写入共享内存
    shm.buf[:len(data) * 8] = data.tobytes()

    print(f"[主进程] 共享内存名称: {shm.name}")
    print(f"[主进程] 初始数据: {list(data)}")

    p = multiprocessing.Process(target=shared_worker, args=(shm.name, len(data)))
    p.start()
    p.join()

    # 读取修改后的数据
    result = array.array('d', shm.buf[:len(data) * 8])
    print(f"[主进程] 最终数据: {list(result)}")

    shm.close()
    shm.unlink()  # 释放共享内存


if __name__ == "__main__":
    print("=== 进程池示例 ===")
    demo_pool()

    print("\n=== Queue 示例 ===")
    demo_queue()

    print("\n=== Pipe 示例 ===")
    demo_pipe()

    print("\n=== SharedMemory 示例 ===")
    demo_shared_memory()
```

### 常见面试题

#### 面试题 1：多进程中的 `if __name__ == "__main__":` 为什么是必须的？

**参考答案：**

在 Windows 和 macOS（spawn 启动方式）上，创建新进程时需要重新导入主模块来重建子进程环境。如果没有 `if __name__ == "__main__":` 保护，主模块中的代码会在子进程导入时被重复执行，导致递归创建子进程，最终引发 `RuntimeError: An attempt has been made to start a new process before the current process has finished its bootstrapping phase`。

Linux 默认使用 `fork` 创建进程，不需要重新导入模块，因此不保护也可能正常工作。但为了保证跨平台兼容性，**所有使用 `multiprocessing` 的代码都应该加上这个保护**。

#### 面试题 2：Queue 和 Pipe 有什么区别？什么时候用 Queue，什么时候用 Pipe？

**参考答案：**

| 特性 | Queue | Pipe |
|------|-------|------|
| 通信方向 | 单向（默认） | 双向（可配置为单向） |
| 连接数 | 多生产者、多消费者 | 点对点（两个进程） |
| 线程/进程安全 | 是（内部加锁） | 需要手动同步 |
| 功能 | 支持超时、队列大小限制 | 简单直接 |
| 底层实现 | 基于 Pipe + Lock | 基于操作系统管道 |

- **使用 Queue**：当有多于两个进程需要通信、需要队列语义（先进先出）、或者需要进程安全的生产者-消费者模型时。
- **使用 Pipe**：当只有两个进程之间需要简单通信，且希望获得更低延迟时。需要注意 Pipe 没有内置的进程安全保护，如果多个线程同时读写同一个连接，需要额外加锁。

---

## 4. 协程与异步 IO（asyncio）

### 概念解释

协程（Coroutine）是 Python 中处理高并发 I/O 的**单线程并发模型**。与多线程不同，协程不由操作系统调度，而是由程序自身在**事件循环（Event Loop）**中调度。当一个协程遇到 I/O 操作（如网络请求）时，它会主动让出控制权，事件循环将 CPU 资源分配给另一个就绪的协程，从而实现"并发"效果。

协程的核心优势在于**极低的上下文切换开销**。线程切换需要操作系统介入，涉及内核态切换和栈保存恢复；而协程切换完全在用户态完成，本质上只是函数调用的切换，速度比线程快数个数量级。同时，由于协程运行在单线程中，天然不存在线程安全问题，不需要加锁。

**asyncio** 是 Python 3.4+ 引入的标准异步 I/O 框架，其核心概念包括：

- **`async def`**：定义协程函数，调用时返回一个协程对象（Coroutine），而不是直接执行。
- **`await`**：在协程中等待另一个可等待对象（协程、Task、Future）完成。`await` 会挂起当前协程，将控制权交还事件循环。
- **事件循环（Event Loop）**：协程调度的心脏。它维护一个就绪队列，不断从队列中取出协程执行，直到它们被 I/O 阻塞或完成。在 Python 3.10+ 中，通常使用 `asyncio.run()` 来自动创建和管理事件循环。
- **Task**：对协程的包装，表示事件循环中的一个"任务"。Task 会尽快在事件循环中执行。通过 `asyncio.create_task()` 创建。
- **Future**：表示一个**未来的结果**，是更低层的抽象。Task 继承自 Future。当异步操作完成时，Future 被设置为包含结果或异常。
- **`asyncio.gather()`**：并发运行多个可等待对象，等待它们全部完成。如果传入 `return_exceptions=True`，其中一个任务的异常不会导致整个 gather 失败，而是将异常作为结果返回。

协程适用于**高并发的 I/O 密集型场景**，如网络爬虫、Web 服务器（FastAPI、Sanic）、数据库连接池、实时通信等。它不适合 CPU 密集型任务，因为协程不会绕过 GIL，长时间计算会阻塞整个事件循环。

### 代码示例

```python
"""
asyncio 核心概念演示：事件循环、Task、Future、gather。
模拟一个高并发的网络爬虫场景。
"""

import asyncio
import random
import time


async def fetch_url(url, delay=None):
    """
    模拟异步 HTTP 请求。
    await asyncio.sleep() 会挂起当前协程，让出事件循环给其他任务。
    """
    actual_delay = delay if delay is not None else random.uniform(0.5, 2.0)
    print(f"[开始] 请求 {url}，预计耗时 {actual_delay:.2f} 秒")
    await asyncio.sleep(actual_delay)  # 模拟网络 I/O，非阻塞！
    print(f"[完成] 请求 {url}")
    return f"{url} 的数据"


async def demo_basic():
    """基础 await 示例：顺序 vs 并发。"""
    urls = ["https://api.example.com/a",
            "https://api.example.com/b",
            "https://api.example.com/c"]

    # === 顺序执行（慢） ===
    print("\n--- 顺序执行 ---")
    start = time.perf_counter()
    for url in urls:
        result = await fetch_url(url, delay=1.0)
        print(f"结果: {result}")
    print(f"顺序执行耗时: {time.perf_counter() - start:.2f} 秒")

    # === 并发执行（快） ===
    print("\n--- 并发执行 ---")
    start = time.perf_counter()
    # gather 会同时启动所有协程，等待全部完成
    results = await asyncio.gather(
        fetch_url(urls[0], delay=1.0),
        fetch_url(urls[1], delay=1.0),
        fetch_url(urls[2], delay=1.0)
    )
    print(f"结果: {results}")
    print(f"并发执行耗时: {time.perf_counter() - start:.2f} 秒")


async def demo_task():
    """Task 示例：后台任务、超时控制。"""
    print("\n--- Task 示例 ---")

    # 创建后台任务（立即开始执行，不需要立即 await）
    task1 = asyncio.create_task(fetch_url("任务-1", delay=3.0), name="后台任务1")
    task2 = asyncio.create_task(fetch_url("任务-2", delay=1.0), name="后台任务2")

    # 此时两个任务已经在事件循环中并发执行了
    # 我们可以先做点别的事情...
    print("[主协程] 任务已启动，先执行其他操作...")
    await asyncio.sleep(0.5)

    # 等待特定任务完成
    result2 = await task2
    print(f"[主协程] 任务2 先完成了: {result2}")

    # 等待剩余任务
    result1 = await task1
    print(f"[主协程] 任务1 也完成了: {result1}")


async def demo_timeout():
    """超时控制：防止协程无限等待。"""
    print("\n--- 超时控制示例 ---")

    try:
        # 设置 2 秒超时
        result = await asyncio.wait_for(
            fetch_url("慢请求", delay=5.0),
            timeout=2.0
        )
        print(f"成功: {result}")
    except asyncio.TimeoutError:
        print("[错误] 请求超时！")


async def demo_future():
    """Future 示例：手动控制异步结果。"""
    print("\n--- Future 示例 ---")

    async def set_future_after_delay(future, delay, value):
        """模拟一个底层异步操作完成后设置 Future 结果。"""
        await asyncio.sleep(delay)
        future.set_result(value)
        print(f"[Future] 已设置结果: {value}")

    loop = asyncio.get_running_loop()
    future = loop.create_future()

    # 启动一个任务，稍后设置 future 的结果
    asyncio.create_task(set_future_after_delay(future, 1.0, "异步结果"))

    print("[主协程] 等待 Future 结果...")
    result = await future  # 挂起直到 future 被设置
    print(f"[主协程] 获得 Future 结果: {result}")


async def demo_semaphore():
    """使用 Semaphore 限制并发数——防止同时发起过多请求。"""
    print("\n--- 信号量限制并发示例 ---")

    # 最多同时允许 2 个并发请求
    semaphore = asyncio.Semaphore(2)
    urls = [f"https://site.com/page-{i}" for i in range(6)]

    async def limited_fetch(url):
        async with semaphore:
            return await fetch_url(url, delay=1.0)

    start = time.perf_counter()
    results = await asyncio.gather(*[limited_fetch(url) for url in urls])
    print(f"6 个请求、最大并发 2，总耗时: {time.perf_counter() - start:.2f} 秒")
    print(f"结果数: {len(results)}")


async def main():
    """主入口：运行所有示例。"""
    await demo_basic()
    await demo_task()
    await demo_timeout()
    await demo_future()
    await demo_semaphore()


if __name__ == "__main__":
    # Python 3.10+ 推荐使用 asyncio.run() 启动事件循环
    asyncio.run(main())
```

### 常见面试题

#### 面试题 1：`async` / `await` 的底层原理是什么？为什么说协程是"非阻塞"的？

**参考答案：**

`async def` 定义的函数返回一个协程对象（Coroutine），它是一个实现了 `__await__` 方法的可等待对象。当执行到 `await` 表达式时，当前协程会将自己挂起（suspend），把控制权交还给事件循环。事件循环会检查其他就绪的协程并执行它们。

协程的"非阻塞"是指它不会阻塞整个线程。当协程遇到 I/O 操作（如 `await asyncio.sleep()`、网络请求）时，它不是傻等，而是主动让出 CPU。但协程本身运行在单线程中，如果协程里写了纯 CPU 计算代码（没有 `await`），它仍然会阻塞事件循环，导致其他协程无法执行。

底层实现上，`asyncio` 使用**生成器**的早期实现（Python 3.5 之前使用 `@asyncio.coroutine` 装饰器配合 `yield from`），现代 Python 则有专门的协程对象，由解释器优化调度。

#### 面试题 2：`asyncio.gather()` 和 `asyncio.wait()` 有什么区别？

**参考答案：**

- **`asyncio.gather(*aws)`**：
  - 并发运行所有传入的可等待对象，等待它们全部完成。
  - 返回一个列表，按传入顺序排列结果。
  - 默认行为：如果任一任务抛出异常，gather 会立即取消其他未完成的任务并将异常向上抛出。可通过 `return_exceptions=True` 改变此行为。

- **`asyncio.wait(aws, return_when=ALL_COMPLETED)`**：
  - 更底层的 API，返回 `(done_set, pending_set)` 两个任务集合。
  - 通过 `return_when` 参数可以控制何时返回：`FIRST_COMPLETED`（任意一个完成）、`FIRST_EXCEPTION`（任意一个异常）、`ALL_COMPLETED`（全部完成，默认）。
  - 更适合需要对完成的任务进行细粒度处理的场景。

**选择建议**：大部分情况下使用 `gather()` 更简洁；当需要部分完成的语义、或者需要对完成/未完成的任务分别处理时，使用 `wait()`。

---

## 5. 并发执行器（ThreadPoolExecutor / ProcessPoolExecutor）

### 概念解释

`concurrent.futures` 模块是 Python 3.2 引入的高级并发接口，提供了统一的 API 来管理线程池和进程池。它的设计目标是**简化并发编程**，隐藏底层 `threading` 和 `multiprocessing` 的复杂性，让开发者用更少的代码实现并发/并行任务调度。

核心组件：

- **`ThreadPoolExecutor`**：管理一个线程池，适合 I/O 密集型任务。内部使用 `threading` 实现，受 GIL 限制。
- **`ProcessPoolExecutor`**：管理一个进程池，适合 CPU 密集型任务。内部使用 `multiprocessing` 实现，每个工作进程有独立的 GIL。
- **`Future` 对象**：表示异步执行的未来结果。通过 `Future` 可以查询任务状态（`running()`、`done()`）、获取结果（`result()`，会阻塞直到有结果）、取消任务（`cancel()`）等。

常用 API：

- `submit(fn, *args, **kwargs)`：提交单个任务，立即返回一个 Future。
- `map(func, *iterables)`：类似内置 `map()`，但并发执行。按输入顺序返回结果。
- `shutdown(wait=True)`：关闭执行器，释放资源。使用上下文管理器（`with` 语句）会自动调用。

`concurrent.futures` 的优势在于**统一的抽象**：无论是线程还是进程，提交任务和获取结果的方式完全一致。这使得在开发阶段可以先使用 `ThreadPoolExecutor` 快速实现，后期发现是 CPU 密集型瓶颈时，只需将 `ThreadPoolExecutor` 替换为 `ProcessPoolExecutor`，代码几乎无需改动。

### 代码示例

```python
"""
concurrent.futures 模块：ThreadPoolExecutor 和 ProcessPoolExecutor。
展示统一 API 下线程池与进程池的使用方式。
"""

import time
import os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed


# ============================================================
# 1. ThreadPoolExecutor——I/O 密集型任务
# ============================================================

def io_bound_task(task_id, duration):
    """模拟 I/O 操作（如网络请求）。"""
    print(f"[线程任务 {task_id}] 开始，线程: {os.getpid()}")
    time.sleep(duration)
    print(f"[线程任务 {task_id}] 完成")
    return f"任务 {task_id} 的结果"


def demo_thread_pool():
    print("=== ThreadPoolExecutor 示例 ===")
    tasks = [(i, 1.0) for i in range(5)]

    with ThreadPoolExecutor(max_workers=3) as executor:
        # 方式 1：submit + Future
        futures = [executor.submit(io_bound_task, tid, dur) for tid, dur in tasks]
        for future in futures:
            print(f"结果: {future.result()}")

        # 方式 2：map（按顺序返回结果）
        # results = executor.map(lambda t: io_bound_task(*t), tasks)
        # for r in results:
        #     print(f"结果: {r}")


# ============================================================
# 2. ProcessPoolExecutor——CPU 密集型任务
# ============================================================

def cpu_bound_task(n):
    """CPU 密集型计算。"""
    print(f"[进程任务] 计算 {n}，进程 PID: {os.getpid()}")
    total = sum(i * i for i in range(n))
    return total


def demo_process_pool():
    print("\n=== ProcessPoolExecutor 示例 ===")
    numbers = [5_000_000, 6_000_000, 7_000_000, 8_000_000, 9_000_000]

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # 使用 as_completed 优先处理先完成的任务
        futures = {executor.submit(cpu_bound_task, n): n for n in numbers}
        for future in as_completed(futures):
            n = futures[future]
            print(f"n={n} 的计算结果: {future.result()}")


# ============================================================
# 3. 异常处理与取消任务
# ============================================================

def task_with_exception(should_fail):
    if should_fail:
        raise ValueError("故意抛出的异常")
    return "成功"


def demo_exception_handling():
    print("\n=== 异常处理示例 ===")
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_ok = executor.submit(task_with_exception, False)
        future_err = executor.submit(task_with_exception, True)

        for name, future in [("正常任务", future_ok), ("异常任务", future_err)]:
            try:
                result = future.result()
                print(f"{name}: {result}")
            except ValueError as e:
                print(f"{name} 捕获异常: {e}")


# ============================================================
# 4. 统一的执行器接口——运行时切换线程/进程
# ============================================================

def run_with_executor(executor_class, func, items, max_workers=None):
    """
    统一的并发执行接口。
    只需更换 executor_class，即可在线程池和进程池间切换。
    """
    kwargs = {"max_workers": max_workers} if max_workers else {}
    with executor_class(**kwargs) as executor:
        results = list(executor.map(func, items))
    return results


def demo_unified_api():
    print("\n=== 统一 API 示例 ===")
    items = [1_000_000, 2_000_000, 3_000_000]

    # CPU 密集型：用进程池
    print("使用 ProcessPoolExecutor:")
    results_process = run_with_executor(ProcessPoolExecutor, cpu_bound_task, items)
    print(f"结果: {results_process}")

    # I/O 密集型：用线程池
    print("\n使用 ThreadPoolExecutor:")
    io_items = [(i, 0.5) for i in range(3)]
    results_thread = run_with_executor(ThreadPoolExecutor,
                                       lambda t: io_bound_task(*t), io_items)
    print(f"结果数: {len(results_thread)}")


if __name__ == "__main__":
    demo_thread_pool()
    demo_process_pool()
    demo_exception_handling()
    demo_unified_api()
```

### 常见面试题

#### 面试题 1：`ThreadPoolExecutor` 中的 `max_workers` 设置多少合适？

**参考答案：**

- **I/O 密集型任务**：`max_workers` 可以设置得较大，通常经验值为 `min(32, os.cpu_count() + 4)`（这是 Python 3.8+ 的默认值）。因为 I/O 操作会释放 GIL，线程大部分时间处于等待状态，多个线程可以交替利用 CPU。
- **CPU 密集型任务**：`max_workers` 通常设置为 `os.cpu_count()` 或 `os.cpu_count() - 1`（留一个核心给操作系统和其他进程），避免过多的进程切换开销。
- **混合型任务**：需要根据实际 I/O 等待时间和 CPU 计算时间的比例来调整，通常通过压测找到最优值。

#### 面试题 2：`Future.result()` 会阻塞吗？如何实现非阻塞地获取结果？

**参考答案：**

是的，`Future.result(timeout=None)` 会阻塞调用线程/进程，直到任务完成并返回结果。如果设置了 `timeout` 参数，超时后会抛出 `TimeoutError`。

实现非阻塞获取结果的方法有：
1. **`as_completed(futures)`**：接受一个 Future 列表，返回一个迭代器，按任务完成的先后顺序产出 Future。这样可以在任意一个任务完成时立即处理，不需要等待全部完成。
2. **`done()` 方法**：检查 Future 是否已完成，配合轮询实现非阻塞检查（不推荐，浪费 CPU）。
3. **`add_done_callback(fn)`**：为 Future 注册一个回调函数，当任务完成时自动调用（注意回调函数在哪个线程执行取决于实现）。
4. **事件循环集成**：在 asyncio 中，可以使用 `loop.run_in_executor()` 将同步代码提交到执行器，返回一个 awaitable 的 Future。

---

## 6. 选择多线程/多进程/协程的场景

### 概念解释

Python 提供了三种主要的并发模型，每种模型都有其最佳适用场景。选择合适的并发策略是后端架构设计中的关键决策，错误的选择不仅不能提升性能，反而可能引入复杂性和额外开销。

**多线程（Threading）**

- **适用场景**：I/O 密集型任务，且任务需要共享内存、频繁访问同一份数据。
- **典型应用**：Web 服务器（如早期的 Werkzeug）、数据库连接池、文件读写密集型应用。
- **优点**：线程间共享内存，通信成本低；启动速度快。
- **缺点**：受 GIL 限制，无法并行执行 Python 字节码；线程安全问题需要加锁保护。

**多进程（Multiprocessing）**

- **适用场景**：CPU 密集型任务，需要充分利用多核 CPU。
- **典型应用**：数据分析、科学计算、图像/视频处理、大规模数据转换。
- **优点**：真正并行，绕过 GIL；进程崩溃隔离，稳定性高。
- **缺点**：进程创建开销大；进程间通信需要序列化（IPC 成本高）；内存占用大（每个进程独立内存空间）。

**协程（Asyncio）**

- **适用场景**：超高并发的 I/O 密集型任务，特别是网络 I/O。
- **典型应用**：高并发 Web 服务器（FastAPI、Sanic）、网络爬虫、WebSocket 服务、API 网关、实时聊天服务。
- **优点**：极高的并发能力（单线程可管理数万甚至数十万个连接）；上下文切换开销极小；无锁编程，避免线程安全问题。
- **缺点**：需要全链路异步（一旦有一个阻塞调用，整个事件循环被阻塞）；不适合 CPU 密集型任务；生态库（异步数据库驱动、HTTP 客户端）不如同步生态成熟；调试难度较高（调用栈不直观）。

**混合模型**也越来越常见：
- `asyncio` + `run_in_executor()`：在协程中调用阻塞的同步代码，将其放到线程池或进程池中执行，避免阻塞事件循环。
- 多进程 + 多线程：每个进程内部再使用线程处理 I/O，最大化资源利用。

### 选择决策树

```
任务类型？
├── CPU 密集型 ────→ 多进程（ProcessPoolExecutor）
│   └── 需要共享大数据？
│       ├── 是 ────→ SharedMemory / NumPy（释放 GIL）
│       └── 否 ────→ 标准多进程
└── I/O 密集型 ────→ 继续判断
    ├── 并发量极高（>1000 连接）？
    │   ├── 是 ────→ 协程（asyncio）
    │   └── 否 ────→ 多线程（ThreadPoolExecutor）
    ├── 全链路可异步？
    │   ├── 是 ────→ 协程
    │   └── 否 ────→ 多线程 / 混合模型
    └── 需要共享状态？
        ├── 是 ────→ 多线程（加锁）
        └── 否 ────→ 协程或多线程均可
```

### 代码示例

```python
"""
混合模型示例：asyncio + ThreadPoolExecutor。
在协程中调用阻塞的同步代码，避免阻塞事件循环。
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
import requests


# 这是一个阻塞的同步函数（第三方库可能没有异步版本）
def blocking_http_get(url):
    """同步 HTTP 请求——会阻塞线程。"""
    print(f"[同步请求] 开始请求 {url}")
    try:
        # requests 是同步库，会阻塞
        resp = requests.get(url, timeout=10)
        return f"{url} -> 状态码 {resp.status_code}"
    except Exception as e:
        return f"{url} -> 错误: {e}"


async def main():
    urls = [
        "https://httpbin.org/get",
        "https://httpbin.org/get",
        "https://httpbin.org/get",
    ]

    print("=== 混合模型：asyncio + ThreadPoolExecutor ===")
    loop = asyncio.get_running_loop()

    # 创建一个线程池
    with ThreadPoolExecutor(max_workers=5) as executor:
        # 将阻塞的同步函数提交到线程池，返回 awaitable 的 Future
        tasks = [
            loop.run_in_executor(executor, blocking_http_get, url)
            for url in urls
        ]

        start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

        for r in results:
            print(r)
        print(f"\n总耗时: {elapsed:.2f} 秒（并发执行）")

    # 对比：纯同步顺序执行
    print("\n=== 对比：纯同步顺序执行 ===")
    start = time.perf_counter()
    for url in urls:
        print(blocking_http_get(url))
    print(f"总耗时: {time.perf_counter() - start:.2f} 秒")


if __name__ == "__main__":
    asyncio.run(main())
```

### 常见面试题

#### 面试题 1：什么时候应该用多线程而不是协程？

**参考答案：**

以下情况应优先选择多线程而非协程：

1. **无法全链路异步**：如果代码依赖大量只有同步版本的第三方库（如早期的 SQLAlchemy、某些科学计算库），改造成异步成本极高，使用线程池更简单。
2. **需要共享可变状态**：多线程通过 Lock 可以安全共享内存，而协程虽然不需要锁，但如果需要在多个独立组件间共享复杂状态，同步代码的思维方式更直观。
3. **并发量不高**：当并发连接数在几十到几百级别时，多线程的开销可以接受，且代码更易于理解和调试。
4. **团队技术栈**：如果团队对 asyncio 的调试、异常处理、上下文变量传播不熟悉，线程池的出错概率更低。

#### 面试题 2：为什么 asyncio 不适合 CPU 密集型任务？如何解决协程中的 CPU 密集型需求？

**参考答案：**

`asyncio` 运行在单线程事件循环中，如果一个协程执行了长时间的 CPU 计算（没有 `await` 点），它会一直占用事件循环，导致其他所有协程都无法执行，整个程序被"卡住"。

解决方法：
1. **`loop.run_in_executor()`**：将 CPU 密集型任务提交到 `ProcessPoolExecutor`（线程池对 CPU 密集型无效，因为 GIL），事件循环继续处理其他 I/O 任务。
2. **使用 C 扩展**：如 NumPy 等库，其底层 C 代码在执行期间会释放 GIL，可以在协程中 `await asyncio.to_thread()`（Python 3.9+）调用它们而不会阻塞事件循环。
3. **多进程 + 协程混合**：主程序使用 asyncio 处理 I/O，CPU 密集型计算交由独立的工作进程池。

---

## 7. 原子操作与线程安全

### 概念解释

**线程安全**是指一个函数或数据结构在多线程环境下被调用时，能够正确处理多个线程同时访问的情况，不会因为执行顺序的不确定性而产生错误的结果。

**原子操作（Atomic Operation）**是指不可被线程调度机制打断的操作，要么全部执行完成，要么完全不执行，不存在中间状态。原子操作是线程安全的基石——如果一个操作是原子的，那么多个线程同时执行它时，不需要额外的锁保护。

在 Python 中，需要明确区分两个层面的"原子性"：

1. **Python 字节码层面的原子性**：由于 GIL 的存在，**单个 Python 字节码指令是原子的**。这意味着，如果一个操作只需要一条字节码就能完成，那么它在多线程下是安全的。例如：
   - 读取或赋值一个变量（引用）是原子的：`x = 1`、`y = x`
   - 列表的 `append()` 是原子的（单个方法调用对应一条 CALL 字节码）
   - 字典的单个键读取/赋值是原子的

2. **非原子操作（需要加锁）**：由多条字节码组成的操作**不是**原子的，多线程下可能出现竞态条件：
   - `i += 1`：**不是**原子的。它实际上分三步：读取 `i`、计算 `i+1`、写回结果。两个线程同时执行可能导致一次增量丢失。
   - `list[0] += 1`：**不是**原子的。
   - `if key not in dict: dict[key] = value`：**不是**原子的。即使单条操作是原子的，组合起来也不是。
   - `L = L + [1]`：**不是**原子的，虽然 `L.append(1)` 是原子的。

Python 的内置数据结构（`list`、`dict`、`set`）在单个方法调用级别是线程安全的，但在组合操作或需要判断-执行的逻辑中，仍然需要加锁。

**竞态条件（Race Condition）**是线程安全问题的典型表现：多个线程以不可预期的顺序访问共享数据，导致结果依赖于执行的时机。解决竞态条件的主要手段就是**互斥锁（Mutex）**，通过锁确保临界区（Critical Section）内同时只有一个线程执行。

### 代码示例

```python
"""
原子操作与线程安全演示。
展示哪些操作看似安全实则不安全，以及如何使用锁保护。
"""

import threading
import time


# ============================================================
# 1. 非原子操作：i += 1 的竞态条件
# ============================================================

def demo_race_condition():
    """演示 i += 1 不是原子操作，多线程下会丢失增量。"""
    counter = 0
    num_threads = 10
    increments_per_thread = 100_000

    def increment():
        nonlocal counter
        for _ in range(increments_per_thread):
            # 这条语句实际上分为 3 步：
            # 1. LOAD counter
            # 2. BINARY_ADD (counter + 1)
            # 3. STORE counter
            # 在这 3 步之间，其他线程可能修改了 counter！
            counter += 1

    threads = [threading.Thread(target=increment) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = num_threads * increments_per_thread
    print(f"[竞态条件演示] 期望值: {expected}, 实际值: {counter}, 丢失: {expected - counter}")


# ============================================================
# 2. 使用 Lock 保护临界区
# ============================================================

def demo_lock_protection():
    """使用 Lock 保护 counter += 1，确保结果正确。"""
    counter = 0
    lock = threading.Lock()
    num_threads = 10
    increments_per_thread = 100_000

    def increment():
        nonlocal counter
        for _ in range(increments_per_thread):
            with lock:
                # 临界区：受锁保护，同一时间只有一个线程能执行
                counter += 1

    threads = [threading.Thread(target=increment) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = num_threads * increments_per_thread
    print(f"[Lock 保护] 期望值: {expected}, 实际值: {counter}")


# ============================================================
# 3. 判断-执行模式的竞态条件
# ============================================================

def demo_check_then_act():
    """
    演示 "if not in then add" 模式的竞态条件。
    即使 dict 的单条操作是原子的，组合起来也不是。
    """
    seen = set()
    duplicates = []
    num_threads = 5

    def add_items(items):
        for item in items:
            # 以下两步不是原子的！
            if item not in seen:    # 步骤 1
                seen.add(item)      # 步骤 2
            else:
                duplicates.append(item)

    # 所有线程操作同一组数据，会有重复添加的风险
    all_items = ["a", "b", "c", "d", "e"] * 20

    threads = []
    chunk_size = len(all_items) // num_threads
    for i in range(num_threads):
        chunk = all_items[i * chunk_size:(i + 1) * chunk_size]
        t = threading.Thread(target=add_items, args=(chunk,))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"[判断-执行模式] set 大小: {len(seen)}, 预期: 5")


# ============================================================
# 4. 使用 Lock 修复判断-执行模式
# ============================================================

def demo_check_then_act_fixed():
    """使用 Lock 修复判断-执行模式的竞态条件。"""
    seen = set()
    lock = threading.Lock()
    num_threads = 5

    def add_items(items):
        for item in items:
            with lock:
                # 临界区内完成完整的判断-执行逻辑
                if item not in seen:
                    seen.add(item)

    all_items = ["a", "b", "c", "d", "e"] * 20
    threads = []
    chunk_size = len(all_items) // num_threads
    for i in range(num_threads):
        chunk = all_items[i * chunk_size:(i + 1) * chunk_size]
        t = threading.Thread(target=add_items, args=(chunk,))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"[修复后] set 大小: {len(seen)}, 预期: 5")


# ============================================================
# 5. Queue 的线程安全性
# ============================================================

from queue import Queue

def demo_queue_threadsafe():
    """
    queue.Queue 是线程安全的，不需要额外加锁。
    这是生产者-消费者的首选实现。
    """
    q = Queue()
    num_items = 1000
    num_threads = 5
    results = []
    lock = threading.Lock()

    def producer():
        for i in range(num_items // num_threads):
            # Queue.put() 是线程安全的，内部已经加锁
            q.put(i)

    def consumer():
        while True:
            try:
                # Queue.get() 也是线程安全的
                item = q.get(timeout=0.5)
                with lock:
                    results.append(item)
                q.task_done()
            except:
                break

    producers = [threading.Thread(target=producer) for _ in range(num_threads)]
    consumers = [threading.Thread(target=consumer) for _ in range(2)]

    for p in producers:
        p.start()
    for c in consumers:
        c.start()

    for p in producers:
        p.join()
    q.join()  # 等待队列处理完毕

    for c in consumers:
        c.join()

    print(f"[Queue 线程安全] 生产: {num_items}, 消费: {len(results)}")


if __name__ == "__main__":
    print("=== 竞态条件演示 ===")
    demo_race_condition()

    print("\n=== Lock 保护演示 ===")
    demo_lock_protection()

    print("\n=== 判断-执行竞态条件 ===")
    demo_check_then_act()

    print("\n=== 判断-执行修复 ===")
    demo_check_then_act_fixed()

    print("\n=== Queue 线程安全 ===")
    demo_queue_threadsafe()
```

### 常见面试题

#### 面试题 1：Python 中 `i += 1` 是原子操作吗？为什么？

**参考答案：**

**不是**。`i += 1` 在 Python 字节码层面被分解为多个步骤：
1. `LOAD_GLOBAL` 或 `LOAD_FAST`（读取变量 `i` 的当前值）
2. `LOAD_CONST`（加载常量 `1`）
3. `BINARY_ADD`（执行加法）
4. `STORE_GLOBAL` 或 `STORE_FAST`（将结果写回变量 `i`）

虽然 GIL 保证**单条字节码**的执行不会被另一个线程打断，但 `i += 1` 涉及多条字节码。在两个线程并发执行时，可能发生以下交错：
- 线程 A 读取 `i = 0`
- 线程 B 读取 `i = 0`
- 线程 A 计算 `0 + 1 = 1`，写回 `i = 1`
- 线程 B 计算 `0 + 1 = 1`，写回 `i = 1`

最终结果是 `1` 而不是 `2`，一次增量丢失了。必须用 `Lock` 保护这类操作。

#### 面试题 2：`list.append()` 是线程安全的吗？`L = L + [1]` 呢？

**参考答案：**

- **`list.append(x)` 是线程安全的**。`append()` 是单个方法调用，在 CPython 中对应一条字节码指令（`CALL_METHOD`），这条指令的执行是原子的（GIL 保护）。多个线程同时对同一个列表调用 `append()`，最终所有元素都会被正确添加，不会破坏列表内部结构。

- **`L = L + [1]` 不是线程安全的**。这个表达式涉及多条字节码：先读取 `L`，创建新列表 `L + [1]`，再将新列表赋值给 `L`。在多线程下，其他线程可能看到中间状态或不一致的引用。此外，如果 `L` 是一个可变对象，这个操作创建了一个新列表并替换引用，与 `append()` 的原地修改语义也不同。

---

## 8. 死锁与避免策略

### 概念解释

**死锁（Deadlock）**是多线程/多进程并发编程中最经典的问题之一。当多个线程（或进程）互相持有对方需要的资源，并且都在等待对方释放资源时，就会形成死锁。所有涉及的线程将永远阻塞，程序挂起。

死锁产生的四个必要条件（Coffman 条件）：

1. **互斥（Mutual Exclusion）**：资源一次只能被一个线程占用。锁天然满足这个条件。
2. **持有并等待（Hold and Wait）**：线程已经持有一个资源，同时又在等待获取另一个被其他线程持有的资源。
3. **非抢占（No Preemption）**：资源不能被强制从线程手中剥夺，只能由持有者主动释放。
4. **循环等待（Circular Wait）**：存在一个线程等待链，链中的每个线程都在等待下一个线程持有的资源，形成一个环。

四个条件**必须同时满足**才会发生死锁。因此，破坏任意一个条件就可以避免死锁。

**常见的死锁场景**：

1. **嵌套锁顺序不一致**：线程 A 先获取锁 1 再获取锁 2，线程 B 先获取锁 2 再获取锁 1。当它们同时分别持有锁 1 和锁 2，然后尝试获取对方持有的锁时，死锁发生。
2. **回调或通知中尝试获取已持有的锁**：使用普通 `Lock` 时，同一线程内嵌套获取已持有的锁会导致死锁（应使用 `RLock`）。
3. **生产者-消费者中的条件变量误用**：在持有 `Condition` 锁的情况下调用外部函数，而外部函数又尝试获取其他锁。

**死锁避免策略**：

1. **锁顺序一致（Lock Ordering）**：为所有锁定义全局唯一的获取顺序，所有线程都按这个顺序获取锁。这样循环等待条件就无法满足。
2. **使用 `RLock`**：在同一线程内需要递归或嵌套获取锁的场景下，使用可重入锁代替普通锁。
3. **使用 `try_lock` / 带超时的获取**：`Lock.acquire(timeout=...)` 允许设置超时时间，超时后放弃获取，避免无限等待。`threading.Lock` 在 Python 3.2+ 支持 `timeout` 参数。
4. **使用更高层的并发工具**：如 `queue.Queue`、线程池等，它们内部已经妥善处理了同步问题，减少了手动加锁的机会。
5. **资源一次性分配**：如果可能，一次性获取所有需要的锁，而不是分步获取。
6. **死锁检测**：维护锁的等待图，检测循环等待。适用于复杂系统，日常开发中较少使用。

### 代码示例

```python
"""
死锁演示与避免策略示例。
包含死锁的产生、锁顺序一致性、超时获取、RLock 等解决方案。
"""

import threading
import time


# ============================================================
# 1. 死锁演示：嵌套锁顺序不一致
# ============================================================

def demo_deadlock():
    """演示典型的死锁场景：两个线程以相反的顺序获取锁。"""
    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def worker_1():
        print("[线程1] 尝试获取 lock_a...")
        lock_a.acquire()
        print("[线程1] 已获得 lock_a")
        time.sleep(0.1)  # 确保线程2也获取了 lock_b

        print("[线程1] 尝试获取 lock_b...")
        lock_b.acquire()  # ← 死锁！线程2持有 lock_b 并等待 lock_a
        print("[线程1] 已获得 lock_b")

        lock_b.release()
        lock_a.release()

    def worker_2():
        print("[线程2] 尝试获取 lock_b...")
        lock_b.acquire()
        print("[线程2] 已获得 lock_b")
        time.sleep(0.1)

        print("[线程2] 尝试获取 lock_a...")
        lock_a.acquire()  # ← 死锁！线程1持有 lock_a 并等待 lock_b
        print("[线程2] 已获得 lock_a")

        lock_a.release()
        lock_b.release()

    t1 = threading.Thread(target=worker_1)
    t2 = threading.Thread(target=worker_2)
    t1.start()
    t2.start()

    # 设置超时，防止演示程序真的卡死
    t1.join(timeout=2)
    t2.join(timeout=2)

    if t1.is_alive() or t2.is_alive():
        print("[死锁演示] 检测到死锁！线程无法完成。\n")


# ============================================================
# 2. 避免策略 1：全局锁顺序
# ============================================================

def demo_lock_ordering():
    """通过全局一致的锁获取顺序避免死锁。"""
    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def safe_worker(name, first_lock, second_lock):
        """所有线程都按相同顺序获取锁：先 a 后 b。"""
        print(f"[{name}] 尝试获取 {first_lock}...")
        with first_lock:
            print(f"[{name}] 已获得 {first_lock}")
            time.sleep(0.1)

            print(f"[{name}] 尝试获取 {second_lock}...")
            with second_lock:
                print(f"[{name}] 已获得 {second_lock}")
                # 执行需要两把锁保护的操作
                print(f"[{name}] 完成工作")

    print("=== 锁顺序一致性避免死锁 ===")
    t1 = threading.Thread(target=safe_worker, args=("线程1", lock_a, lock_b))
    t2 = threading.Thread(target=safe_worker, args=("线程2", lock_a, lock_b))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("所有线程顺利完成！\n")


# ============================================================
# 3. 避免策略 2：带超时的锁获取
# ============================================================

def demo_timeout_lock():
    """使用 timeout 参数，超时后放弃获取，打破死锁。"""
    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def timeout_worker(name, first_lock, second_lock):
        acquired_first = first_lock.acquire(timeout=1)
        if not acquired_first:
            print(f"[{name}] 获取第一把锁超时，放弃执行")
            return

        print(f"[{name}] 已获得第一把锁")
        time.sleep(0.2)

        acquired_second = second_lock.acquire(timeout=1)
        if not acquired_second:
            print(f"[{name}] 获取第二把锁超时，释放已持有的锁并退出")
            first_lock.release()
            return

        print(f"[{name}] 已获得两把锁，执行工作")
        second_lock.release()
        first_lock.release()

    print("=== 超时机制避免无限等待 ===")
    # 故意使用相反的顺序来触发潜在死锁
    t1 = threading.Thread(target=timeout_worker, args=("线程1", lock_a, lock_b))
    t2 = threading.Thread(target=timeout_worker, args=("线程2", lock_b, lock_a))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("至少一个线程因超时而放弃，避免了永久死锁\n")


# ============================================================
# 4. 避免策略 3：RLock 解决同线程重入
# ============================================================

def demo_rlock_solution():
    """
    演示 RLock 解决同一线程内的嵌套加锁问题。
    如果使用普通 Lock，嵌套获取会导致死锁。
    """
    # 使用普通 Lock 会导致死锁
    # lock = threading.Lock()
    # 使用 RLock 可以安全重入
    lock = threading.RLock()

    def outer_function():
        with lock:
            print("[RLock] 进入 outer_function，获取锁")
            inner_function()  # 嵌套调用也需要获取同一把锁
        print("[RLock] 离开 outer_function，释放锁")

    def inner_function():
        with lock:
            print("[RLock] 进入 inner_function，成功重入获取锁")
        print("[RLock] 离开 inner_function，计数减一")

    print("=== RLock 解决同线程嵌套死锁 ===")
    outer_function()
    print("执行完成！\n")


# ============================================================
# 5. 避免策略 4：使用上下文管理器统一管理
# ============================================================

from contextlib import contextmanager

@contextmanager
def acquire_locks(*locks, timeout=None):
    """
    上下文管理器：按固定顺序获取多把锁，支持超时。
    如果无法获取所有锁，则释放已获取的锁。
    """
    acquired = []
    try:
        for lock in locks:
            if timeout is not None:
                got_it = lock.acquire(timeout=timeout)
            else:
                got_it = lock.acquire(blocking=False)
            if not got_it:
                # 获取失败，回滚已获取的锁
                raise RuntimeError(f"无法获取锁 {lock}")
            acquired.append(lock)
        yield
    finally:
        # 按相反顺序释放锁
        for lock in reversed(acquired):
            lock.release()


def demo_context_manager():
    """使用上下文管理器安全地管理多把锁。"""
    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def safe_worker(name):
        try:
            # 按固定顺序一次性获取所有锁
            with acquire_locks(lock_a, lock_b, timeout=2):
                print(f"[{name}] 成功获取所有锁，执行工作")
                time.sleep(0.5)
        except RuntimeError as e:
            print(f"[{name}] {e}")

    print("=== 上下文管理器统一管理锁 ===")
    t1 = threading.Thread(target=safe_worker, args=("线程1",))
    t2 = threading.Thread(target=safe_worker, args=("线程2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("执行完成！\n")


# ============================================================
# 6. 实际生产中的最佳实践：减少锁的持有范围
# ============================================================

def demo_minimize_lock_scope():
    """演示如何最小化临界区，降低死锁概率。"""
    data = {"counter": 0, "items": []}
    lock = threading.Lock()

    def bad_practice():
        """反模式：在持有锁的同时执行耗时操作。"""
        with lock:
            data["counter"] += 1
            time.sleep(1)  # 在临界区内做 I/O 或耗时计算！
            data["items"].append("item")

    def good_practice():
        """最佳实践：只保护必要的最小代码块。"""
        # 步骤 1：准备数据（不需要锁）
        new_item = f"item-{threading.current_thread().name}"

        # 步骤 2：只保护对共享状态的修改
        with lock:
            data["counter"] += 1
            data["items"].append(new_item)

        # 步骤 3：后续处理（不需要锁）
        time.sleep(1)

    print("=== 最小化锁范围 ===")
    print("反模式：在临界区内执行耗时操作，增加死锁风险和竞争")
    print("最佳实践：只保护最短的必要代码段")


if __name__ == "__main__":
    print("=== 死锁演示（注意：会超时） ===")
    demo_deadlock()

    demo_lock_ordering()
    demo_timeout_lock()
    demo_rlock_solution()
    demo_context_manager()
    demo_minimize_lock_scope()
```

### 常见面试题

#### 面试题 1：死锁的四个必要条件是什么？如何在实际开发中避免死锁？

**参考答案：**

死锁的四个必要条件（Coffman 条件）：
1. **互斥**：资源不可共享。
2. **持有并等待**：持有资源的同时请求新资源。
3. **非抢占**：资源不能被强制释放。
4. **循环等待**：存在一个线程等待链形成闭环。

实际开发中的避免策略：
1. **锁顺序一致**：为所有锁定义全局顺序，所有线程严格按此顺序获取。这是最有效的方法。
2. **超时机制**：使用 `acquire(timeout=...)`，超时后释放已持有的锁并重试。
3. **使用 RLock**：避免同一线程内的嵌套死锁。
4. **最小化锁粒度**：只在最必要的代码段持有锁，减少锁被持有的时间。
5. **使用更高级的并发工具**：如 `queue.Queue`、线程池，减少手动管理锁的需求。
6. **一次性获取所有锁**：如果必须同时持有多把锁，设计一个机制同时获取或全部放弃。

#### 面试题 2：如果线上系统出现了死锁，你如何排查和解决？

**参考答案：**

排查步骤：
1. **确认症状**：服务响应变慢或完全无响应，CPU 使用率可能不高（线程都在等待），日志停止输出。
2. **获取线程栈**：使用 `py-spy`、`gdb` 或 `faulthandler` 导出所有线程的调用栈。Python 3.3+ 可通过 `faulthandler.dump_traceback()` 或发送 `SIGUSR1` 信号获取。
3. **分析等待链**：查看各线程的栈帧，找出哪些线程在等待哪些锁（Lock 对象），识别循环等待模式。
4. **代码审查**：定位到持锁和等锁的代码位置，检查锁的获取顺序是否一致。

解决和修复：
1. **短期**：重启服务恢复（治标不治本）。
2. **中期**：在关键路径上增加锁超时和降级逻辑。
3. **长期**：
   - 统一锁的获取顺序；
   - 将大锁拆分为细粒度锁；
   - 引入无锁数据结构或消息队列替代共享状态；
   - 增加监控和报警，在死锁即将发生前检测锁等待时间过长并告警。

---

> **本章小结**
>
> Python 并发编程的核心在于理解 GIL 的影响，并根据任务类型选择正确的并发模型：多进程突破 GIL 实现真正的并行计算，多线程适合 I/O 密集型且需要共享内存的场景，协程则在超高并发网络 I/O 中表现卓越。无论选择哪种模型，线程安全和死锁预防都是必须时刻警惕的问题——最小化临界区、统一锁顺序、优先使用高层抽象，是写出健壮并发代码的三大原则。




---


# 第 6 章：Linux & 部署 & 中间件

本章面向 Python 后端开发面试，系统梳理 Linux 运维、服务部署、中间件配置等高频考点。理解这些知识不仅是为了"背八股"，更是为了在真实生产环境中能够快速定位问题、保障服务稳定运行。

---

## 1. Linux 常用命令与 Shell 脚本

### 概念解释

Linux 是绝大多数服务器端的操作系统，掌握常用命令是后端开发的基本功。日常工作中，我们需要通过 SSH 远程登录服务器，查看进程状态、排查日志、管理文件、监控系统资源等。Shell 脚本则是将一系列命令自动化执行的利器，常用于定时任务（crontab）、部署脚本、日志清理等场景。

Linux 命令的核心设计理念是"一切皆文件"：进程是文件（`/proc`）、设备是文件（`/dev`）、网络配置也是文件。理解这个理念，就能更快上手各种命令。命令之间通过管道（`|`）串联，实现强大的组合能力，比如 `ps aux | grep python | awk '{print $2}' | xargs kill -9` 这条链式命令，可以精准杀掉所有 Python 进程。

常用的命令族包括：文件操作（`ls`、`find`、`tar`）、文本处理（`grep`、`awk`、`sed`、`cut`）、进程管理（`ps`、`top`、`htop`、`kill`）、网络诊断（`netstat`、`ss`、`curl`、`ping`、`tcpdump`）、磁盘与内存（`df`、`du`、`free`）。其中 `awk` 和 `sed` 是面试高频考点，掌握它们的基本用法能显著提升日志分析效率。

Shell 脚本方面，需要理解变量、条件判断、循环、函数、管道和重定向等基础语法。编写脚本时要注意安全性：变量加引号防止空格问题、使用 `set -e` 让脚本遇错即停、避免在脚本中硬编码密码。生产环境推荐用 `#!/bin/bash` 并开启严格模式（`set -euo pipefail`），这能捕获大部分低级错误。

### 代码/配置示例

```bash
#!/bin/bash
# 严格模式：遇到错误立即退出，未定义变量报错，管道错误也能捕获
set -euo pipefail

# 变量定义（等号两侧不能有空格）
APP_NAME="myapp"
LOG_DIR="/var/log/${APP_NAME}"

# 检查目录是否存在，不存在则创建
if [[ ! -d "$LOG_DIR" ]]; then
    mkdir -p "$LOG_DIR"
    echo "创建日志目录: $LOG_DIR"
fi

# 循环示例：清理 7 天前的日志
echo "开始清理 7 天前的日志文件..."
find "$LOG_DIR" -name "*.log" -type f -mtime +7 | while read -r file; do
    echo "删除: $file"
    rm -f "$file"
done

# 函数定义：获取磁盘使用率并判断是否需要报警
check_disk() {
    local threshold=80
    # df -h 取根分区使用率（去掉 % 符号）
    local usage
    usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [[ "$usage" -gt "$threshold" ]]; then
        echo "警告：磁盘使用率 ${usage}% 超过阈值 ${threshold}%"
        return 1
    else
        echo "磁盘使用率正常: ${usage}%"
        return 0
    fi
}

check_disk

# 常用组合命令示例
# 1. 查找占用端口 8080 的进程并终止
# lsof -i :8080 | awk 'NR>1 {print $2}' | xargs kill -9

# 2. 统计 access.log 中每个 IP 的访问次数，取 Top 10
# awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -n 10

# 3. 实时监控 Python 进程内存占用
# ps aux | grep python | grep -v grep | awk '{print $2, $4, $11}'
```

### 常见面试题

#### Q1：`ps aux` 和 `ps -ef` 有什么区别？

**参考答案：** 两者都能查看进程信息，但输出格式和兼容性略有不同。`ps aux` 使用 BSD 风格（无 `-`），显示 `%CPU`、`%MEM`、`VSZ`、`RSS` 等内存和 CPU 使用率字段，信息更详细，适合查看资源占用。`ps -ef` 使用标准 UNIX 风格（带 `-`），显示 `PPID`（父进程 ID）和更精确的 `C`（CPU 利用率），并且输出格式更规范，适合脚本中解析（`ps -ef | grep xxx`）。日常排查推荐 `ps aux`，脚本化场景推荐 `ps -ef`。

#### Q2：解释一下 `awk '{print $2}'` 的工作原理？

**参考答案：** `awk` 是一款强大的文本处理工具，按行读取输入并自动按空白字符分割成字段。`$0` 代表整行，`$1` 是第 1 个字段，`$2` 是第 2 个字段，以此类推。`awk '{print $2}'` 的作用是对每一行输出第 2 个字段。它默认以空格或制表符作为分隔符，也可以通过 `-F` 指定自定义分隔符，比如 `awk -F':' '{print $1}' /etc/passwd` 按冒号分割并输出用户名。`awk` 还支持条件过滤（`awk '$3 > 100 {print $1}'`）、内置变量（`NR` 行号、`NF` 字段数）和算术运算，是日志分析的利器。

---

## 2. 进程管理（systemd、supervisor）

### 概念解释

在生产环境中，Python 应用（如 Django/Flask/FastAPI）不能简单地用 `python app.py` 前台启动，因为 SSH 断开后进程会被终止。我们需要进程管理工具来守护（daemonize）应用，实现开机自启、崩溃自动重启、日志管理和资源限制等功能。

**systemd** 是现代 Linux 发行版（CentOS 7+、Ubuntu 16+）的标准初始化系统，已经取代了传统的 SysV init。systemd 通过"单元文件"（`.service`）定义服务，提供了强大的依赖管理、资源控制（cgroups）、定时任务（`timer`）和日志统一管理（`journald`）能力。它的设计哲学是"并行启动"，大幅缩短了系统启动时间。对于后端服务，systemd 是最推荐的部署方式，因为它与操作系统深度集成，稳定性和性能都优于第三方工具。

**supervisor** 是一个用 Python 编写的进程管理工具，通过 `supervisord` 守护进程和 `supervisorctl` 客户端进行管理。它的配置比 systemd 更简单直观，支持 Web 界面监控，且跨平台兼容（在 macOS 上也能用）。supervisor 的缺点是它本身作为一个进程运行，如果它崩溃了，管理的所有子进程都会失效，因此需要配置 systemd 来守护 supervisor 自身。supervisor 适合快速部署、开发测试环境，或者对 systemd 不熟悉的场景。

选择建议：生产服务器直接用 systemd 管理服务；本地开发或需要 Web 管理界面时用 supervisor；也可以两者结合，systemd 守护 supervisor，supervisor 管理业务进程。

### 代码/配置示例

**systemd 服务文件示例**（`/etc/systemd/system/myapp.service`）：

```ini
[Unit]
# 服务描述
Description=My Python Web Application
# 在网络服务启动后再启动本服务
After=network.target

[Service]
# 以指定的用户和组运行（避免用 root）
User=appuser
Group=appuser

# 工作目录
WorkingDirectory=/opt/myapp

# 启动命令，使用绝对路径
ExecStart=/opt/myapp/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:application

# 优雅重启命令（发送 HUP 信号给 Gunicorn 主进程）
ExecReload=/bin/kill -s HUP $MAINPID

# 停止命令
ExecStop=/bin/kill -s TERM $MAINPID

# 崩溃后自动重启策略：on-failure 表示仅在异常退出时重启
Restart=on-failure
# 10 秒内最多重启 3 次，超过则标记为失败
RestartSec=5
StartLimitInterval=10
StartLimitBurst=3

# 标准输出和错误重定向到 journal（可用 journalctl 查看）
StandardOutput=journal
StandardError=journal

# 环境变量文件（每行一个 KEY=VALUE）
EnvironmentFile=/opt/myapp/.env

[Install]
# 多用户模式下启用开机自启
WantedBy=multi-user.target
```

**常用 systemd 命令**：

```bash
# 重新加载 systemd 配置（修改 .service 文件后必须执行）
sudo systemctl daemon-reload

# 启动、停止、重启、查看状态
sudo systemctl start myapp
sudo systemctl stop myapp
sudo systemctl restart myapp
sudo systemctl status myapp

# 开机自启管理
sudo systemctl enable myapp   # 启用开机自启
sudo systemctl disable myapp  # 禁用开机自启

# 查看日志（-u 指定服务，-f 实时跟踪，--since 指定时间范围）
sudo journalctl -u myapp -f --since "1 hour ago"

# 查看服务是否配置正确
sudo systemctl cat myapp
```

**supervisor 配置示例**（`/etc/supervisor/conf.d/myapp.conf`）：

```ini
[program:myapp]
; 启动命令
command=/opt/myapp/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:application

; 工作目录
directory=/opt/myapp

; 以 appuser 用户运行
user=appuser

; 自动启动、自动重启
autostart=true
autorestart=true

; 启动失败重试次数
startretries=3

; 优雅停止等待时间（秒）
stopwaitsecs=10

; 标准输出和错误日志路径
stdout_logfile=/var/log/myapp/out.log
stderr_logfile=/var/log/myapp/err.log

; 日志轮转大小（超过 10MB 自动切分）
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
```

**supervisor 常用命令**：

```bash
# 重新加载配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动、停止、重启、查看状态
sudo supervisorctl start myapp
sudo supervisorctl stop myapp
sudo supervisorctl restart myapp
sudo supervisorctl status myapp

# 进入交互式控制台
sudo supervisorctl
```

### 常见面试题

#### Q1：systemd 和 supervisor 各有什么优缺点？生产环境怎么选？

**参考答案：** systemd 是 Linux 系统级初始化工具，与内核深度集成，支持 cgroups 资源限制、依赖排序、定时任务等高级功能，且无需额外安装。缺点在于学习曲线较陡，配置语法对新手不够友好。supervisor 是 Python 编写的应用级进程管理器，配置简单，自带 Web 界面，跨平台兼容。缺点是它自身也是一个进程（需要被守护），且功能不如 systemd 丰富。生产环境首选 systemd，因为它是系统标准组件，稳定性经过广泛验证；supervisor 更适合开发环境、macOS 部署，或需要 Web 管理界面的场景。实践中也可以两者结合：systemd 守护 supervisord，supervisor 管理业务进程。

#### Q2：Gunicorn 收到 HUP 信号后会做什么？为什么这是优雅重启？

**参考答案：** Gunicorn 主进程收到 `HUP` 信号后，会重新加载配置并启动新的 worker 进程。新 worker 启动完成后，主进程向旧 worker 发送 `TERM` 信号，旧 worker 在处理完当前请求后才会退出。这种"先启后停"的机制确保了服务在整个重启过程中不中断，已经建立的连接不会丢失。与之对比，`KILL` 信号（`-9`）会强制终止进程，可能导致正在处理的请求中断、数据库连接异常、事务回滚等问题。因此生产环境的重启脚本应该使用 `kill -HUP` 或 `systemctl reload`，而不是 `restart`。

---

## 3. Nginx 配置与反向代理、负载均衡

### 概念解释

Nginx（发音 "engine-x"）是一款高性能的 HTTP 和反向代理服务器，以事件驱动架构著称，能够用极少的内存同时处理数万个并发连接。在 Python Web 应用架构中，Nginx 通常位于最前端，承担静态文件服务、反向代理、负载均衡、SSL 终端、限流和缓存等多重职责。

**反向代理**是 Nginx 的核心功能之一。客户端直接与 Nginx 通信，Nginx 根据配置将请求转发到后端的 Gunicorn/uWSGI 等 WSGI 服务器。这种架构的优势在于：Nginx 擅长处理静态文件和维持大量慢速连接，而 Python 应用服务器擅长运行业务逻辑，两者各司其职；Nginx 可以在前端统一处理 HTTPS 加解密（SSL 终端），减轻后端压力；Nginx 还能通过缓冲机制（`proxy_buffering`）平滑后端响应，避免慢客户端拖垮应用服务器。

**负载均衡**是在有多台后端服务器时，Nginx 按照特定算法将请求分发到不同节点。常用算法包括轮询（`round_robin`，默认）、按权重分配（`weight`）、IP 哈希（`ip_hash`，保持会话一致性）、最少连接（`least_conn`）等。负载均衡能提升系统吞吐量和可用性：当某台服务器故障时，Nginx 会自动将其摘除（配合 `max_fails` 和 `fail_timeout`）；当流量增长时，可以横向添加服务器而无需修改 Nginx 核心配置。

此外，Nginx 还常用于：静态文件直出（`location /static/` 和 `/media/`）、URL 重写与跳转（`rewrite`、`return`）、访问控制（`allow`/`deny`）、请求限速（`limit_req_zone`）和连接数限制（`limit_conn_zone`）。

### 代码/配置示例

**基础反向代理配置**（单后端）：

```nginx
# /etc/nginx/sites-available/myapp

server {
    # 监听 80 端口，server_name 填写域名或 IP
    listen 80;
    server_name api.example.com;

    # 客户端请求体最大大小（防止大文件上传被拒绝）
    client_max_body_size 20M;

    # 日志配置
    access_log /var/log/nginx/myapp_access.log;
    error_log /var/log/nginx/myapp_error.log warn;

    # 静态文件直接由 Nginx 提供，不转发到后端
    location /static/ {
        alias /opt/myapp/static/;   # 注意：末尾的 / 要与 location 匹配
        expires 30d;                 # 客户端缓存 30 天
        add_header Cache-Control "public, immutable";
    }

    # 媒体文件同理
    location /media/ {
        alias /opt/myapp/media/;
        expires 7d;
    }

    # 健康检查接口（供负载均衡器或监控使用）
    location /health {
        access_log off;              # 健康检查日志太频繁，关闭
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    # 所有其他请求转发到 Gunicorn
    location / {
        # 转发到本机 8000 端口
        proxy_pass http://127.0.0.1:8000;

        # 关键：将 Host 头传递给后端，否则后端无法识别域名
        proxy_set_header Host $host;

        # 传递真实客户端 IP，后端才能获取到访问者的真实地址
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # 传递协议（http/https），后端据此生成正确的 URL
        proxy_set_header X-Forwarded-Proto $scheme;

        # 启用缓冲，防止慢客户端拖垮后端
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
}
```

**负载均衡配置**（多后端）：

```nginx
# 定义 upstream 组，位于 http 块内（通常是 nginx.conf 的 http {} 中）
upstream app_backend {
    # 轮询 + 权重配置
    server 192.168.1.10:8000 weight=3 max_fails=3 fail_timeout=30s;
    server 192.168.1.11:8000 weight=2 max_fails=3 fail_timeout=30s;
    server 192.168.1.12:8000 backup;  # 备份服务器，仅当主节点全部不可用时启用

    # 保持会话一致性（根据客户端 IP 哈希选择后端）
    # ip_hash;

    # 最少连接算法（适合请求处理时长差异大的场景）
    # least_conn;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://app_backend;  # 使用 upstream 名称
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 连接超时配置
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

**HTTPS 配置（SSL 终端）**：

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;

    # SSL 证书路径
    ssl_certificate /etc/nginx/ssl/api.example.com.crt;
    ssl_certificate_key /etc/nginx/ssl/api.example.com.key;

    # 安全加固：仅使用 TLS 1.2/1.3，禁用不安全的算法
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;

    # 其他 location 配置同上...
}

# HTTP 自动跳转到 HTTPS
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}
```

### 常见面试题

#### Q1：Nginx 的反向代理和正向代理有什么区别？

**参考答案：** 正向代理是客户端的代理，代理服务器代表客户端向目标服务器发起请求，隐藏的是客户端的身份（比如翻墙用的代理）。反向代理是服务器的代理，客户端直接访问反向代理服务器，由它来决定将请求转发给哪台后端服务器，隐藏的是后端服务器的真实身份和拓扑结构。在 Python Web 架构中，Nginx 作为反向代理，客户端只知道 Nginx 的地址，不知道背后有多少台 Gunicorn 服务器。反向代理的核心价值在于：负载均衡、SSL 终端、安全防护（隐藏后端真实 IP）、静态文件加速和统一入口管理。

#### Q2：什么是 Nginx 的 `upstream` 模块？有哪些常用的负载均衡算法？

**参考答案：** `upstream` 是 Nginx 中定义后端服务器组的模块，将多台服务器抽象为一个逻辑单元，供 `proxy_pass` 引用。常用负载均衡算法包括：（1）**轮询（round_robin）**：默认算法，按请求顺序依次分发到各服务器，可配合 `weight` 调整权重；（2）**IP 哈希（ip_hash）**：根据客户端 IP 计算哈希值，同一 IP 始终落到同一后端，适合需要会话保持的场景（但现代应用更推荐用分布式 Session 或 JWT 替代）；（3）**最少连接（least_conn）**：将请求分配给当前连接数最少的服务器，适合请求处理时长差异大的场景；（4）**加权轮询**：在轮询基础上按服务器性能分配不同权重。此外还有第三方模块支持的 `fair`（按响应时间分配）和一致性哈希等高级算法。

---

## 4. Docker 基础（Dockerfile、Compose、镜像优化）

### 概念解释

Docker 是一个开源的容器化平台，它通过操作系统级虚拟化技术（Linux 内核的 `cgroups` 和 `namespaces`）将应用及其依赖打包到一个轻量级、可移植的容器中。与传统虚拟机（VM）相比，Docker 容器共享宿主机的操作系统内核，启动速度以秒计，资源占用仅为 MB 级别，而虚拟机需要完整的操作系统，启动分钟级，占用 GB 级资源。

**Dockerfile** 是构建 Docker 镜像的文本脚本，每一条指令（`FROM`、`RUN`、`COPY`、`CMD` 等）都会在镜像中创建一个只读层（layer）。理解层的概念至关重要：Docker 使用联合文件系统（UnionFS），镜像由多层叠加而成，容器运行时在最上层添加可写层。层是可以被缓存的，如果某一层的内容没有变化，Docker 构建时会直接使用缓存而不重新执行。因此，编写 Dockerfile 的核心优化原则之一是**把变化频率低的指令放在前面，变化频率高的放在后面**，最大化缓存命中率。

**Docker Compose** 是用于定义和运行多容器应用的工具。通过一个 `docker-compose.yml` 文件，可以用声明式的方式配置应用的服务、网络、数据卷和依赖关系，然后一条 `docker-compose up -d` 命令启动整个应用栈。它特别适合开发环境和测试环境，以及中小型项目的生产部署。

**镜像优化**是 Docker 实践中的重点。Python 镜像常见的优化手段包括：选用精简的基础镜像（`python:3.11-slim` 或 `python:3.11-alpine`）、多阶段构建（multi-stage，先在一个"胖"镜像中编译依赖，再只把编译产物复制到"瘦"镜像中运行）、合并 `RUN` 指令减少层数、及时清理缓存（`apt-get clean`、不缓存 pip：`pip install --no-cache-dir`）。一个优化后的 Python 生产镜像可以从 GB 级压缩到 100MB 以内。

### 代码/配置示例

**优化后的 Dockerfile**（多阶段构建 + slim 基础镜像）：

```dockerfile
# ==========================================
# 第一阶段：构建阶段（包含编译工具，体积较大）
# ==========================================
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 先单独复制 requirements.txt，利用 Docker 层缓存：
# 只有当 requirements.txt 变化时才重新安装依赖
COPY requirements.txt .

# 安装编译依赖（某些 Python 包需要 gcc 等编译器）
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    # 创建虚拟环境并安装依赖
    python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    # 清理：删除编译工具和 apt 缓存，减小镜像体积
    apt-get purge -y --auto-remove gcc && \
    rm -rf /var/lib/apt/lists/*

# ==========================================
# 第二阶段：运行阶段（仅包含运行时必需的文件）
# ==========================================
FROM python:3.11-slim AS runner

# 安全：创建非 root 用户运行应用
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 从构建阶段复制虚拟环境（包含所有已安装的包）
COPY --from=builder /opt/venv /opt/venv

# 将虚拟环境的 bin 加入 PATH
ENV PATH="/opt/venv/bin:$PATH"

# 设置工作目录并复制应用代码
WORKDIR /app
COPY --chown=appuser:appgroup . .

# 切换到非 root 用户
USER appuser

# 暴露端口（仅作为文档说明，实际映射通过 -p 参数）
EXPOSE 8000

# 健康检查：每 30 秒访问 /health，连续 3 次失败则认为容器不健康
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 容器启动时执行的命令
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:application"]
```

**docker-compose.yml 示例**（Web + 数据库 + Redis）：

```yaml
version: "3.8"

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: myapp_web
    # 端口映射：宿主机 8000 → 容器 8000
    ports:
      - "8000:8000"
    # 环境变量从 .env 文件加载
    env_file:
      - .env
    # 数据卷：代码修改后无需重建镜像即可生效（仅开发环境）
    volumes:
      - .:/app
      - /app/__pycache__  # 匿名卷：防止宿主机缓存污染容器
    # 依赖 db 和 redis 先启动
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    # 自动重启策略
    restart: unless-stopped
    # 资源限制
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M

  db:
    image: postgres:15-alpine
    container_name: myapp_db
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # 从 .env 读取
    volumes:
      # 命名卷：持久化数据库数据，容器删除后数据不丢失
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
    # Postgres 自带健康检查
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d myapp"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: myapp_redis
    volumes:
      - redis_data:/data
    restart: unless-stopped
    # 开启 AOF 持久化
    command: redis-server --appendonly yes

  # Nginx 反向代理（可选，也可用宿主机的 Nginx）
  nginx:
    image: nginx:alpine
    container_name: myapp_nginx
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./static:/usr/share/nginx/html/static:ro
    depends_on:
      - web
    restart: unless-stopped

# 命名卷定义（Docker 自动管理）
volumes:
  postgres_data:
  redis_data:
```

**常用 Docker 命令**：

```bash
# 构建镜像（-t 指定标签，. 表示当前目录）
docker build -t myapp:latest .

# 运行容器（-d 后台运行，-p 端口映射，--name 指定容器名）
docker run -d -p 8000:8000 --name myapp_container myapp:latest

# 查看运行中的容器
docker ps

# 查看容器日志（-f 实时跟踪）
docker logs -f myapp_container

# 进入容器内部调试
docker exec -it myapp_container /bin/bash

# Compose 命令（需在 docker-compose.yml 所在目录执行）
docker-compose up -d          # 后台启动所有服务
docker-compose down           # 停止并删除容器
docker-compose down -v        # 同时删除命名卷（慎用，会丢失数据）
docker-compose logs -f web    # 实时查看 web 服务日志
docker-compose exec web bash  # 进入 web 容器
docker-compose build          # 重建镜像
docker-compose up -d --build  # 重建后启动
```

### 常见面试题

#### Q1：Docker 的镜像分层（Layer）是什么？为什么层数越少越好？

**参考答案：** Docker 镜像采用联合文件系统（UnionFS），由一系列只读层叠加而成。Dockerfile 中的每条指令（`FROM`、`RUN`、`COPY` 等）都会创建一个新层。层是可以被缓存和复用的，如果某一层没有变化，构建时会直接使用缓存。层数越少，镜像体积越小（因为每层只存储与上一层的差异），构建速度越快，推送到镜像仓库的流量也越少。优化方法包括：合并多个 `RUN` 命令（用 `&&` 连接）、将不常变化的指令（如安装依赖）放在前面、使用多阶段构建只保留最终产物。但要注意，过度合并不利于缓存，比如把代码和依赖放在同一个 `RUN` 中，每次代码改动都会重新安装所有依赖。

#### Q2：什么是 Docker 的多阶段构建（Multi-stage Build）？举一个 Python 项目的实际例子。

**参考答案：** 多阶段构建允许在一个 Dockerfile 中使用多个 `FROM` 指令，每个 `FROM` 开启一个新阶段。前面阶段可以包含编译工具（如 gcc）和构建缓存，后面阶段只复制前面阶段生成的产物，最终镜像不包含任何编译依赖，大幅减小体积。以 Python 项目为例：第一阶段使用 `python:3.11-slim` 安装 gcc、创建虚拟环境并 `pip install` 所有依赖；第二阶段同样基于 `python:3.11-slim`，但只用 `COPY --from=builder` 把第一阶段的虚拟环境复制过来，然后复制应用代码，设置非 root 用户运行。这样最终镜像只包含运行时必需的 Python 包和代码，体积可能从 1GB+ 降至 150MB 以下。

---

## 5. CI/CD 基础（GitHub Actions / GitLab CI）

### 概念解释

CI/CD（持续集成 / 持续部署）是现代软件开发的核心实践，旨在通过自动化流水线将代码变更快速、可靠地交付到生产环境。**持续集成（CI）** 指开发人员频繁地将代码合并到主分支，每次合并都自动触发构建和测试，尽早发现集成问题。**持续部署（CD）** 则是在 CI 通过后，自动将代码部署到测试环境或生产环境，缩短交付周期。

理解 CI/CD 的价值不能停留在"自动化"三个字上。它的核心收益在于：（1）**快速反馈**：代码提交后几分钟内就能知道是否破坏了构建或测试，问题定位更容易；（2）**降低发布风险**：小批量、高频次的发布比一次性发布大量变更加安全，出现问题时回滚范围更小；（3）**标准化流程**：将构建、测试、部署步骤固化在配置文件中，消除"在我机器上能跑"的问题；（4）**释放人力**：开发人员不再需要手动打包、上传、重启服务。

**GitHub Actions** 是 GitHub 提供的 CI/CD 服务，与代码仓库深度集成。它使用 YAML 定义工作流（Workflow），通过事件（`push`、`pull_request`、`schedule` 等）触发。Actions 的核心概念包括：工作流（Workflow，顶级配置）、任务（Job，并行或串行执行）、步骤（Step，Job 内的命令序列）和动作（Action，可复用的功能模块，官方市场有数千个）。

**GitLab CI** 是 GitLab 内置的 CI/CD 工具，配置写在仓库根目录的 `.gitlab-ci.yml` 中。它使用** runner** 执行流水线任务，概念与 GitHub Actions 类似，但增加了**阶段（Stage）**的显式定义（如 `build`、`test`、`deploy`），同一阶段的 Job 并行执行，不同阶段按顺序执行。

Python 项目的典型 CI/CD 流水线包括：检出代码 → 安装依赖 → 代码风格检查（`flake8`、`black`、`isort`）→ 静态类型检查（`mypy`）→ 运行单元测试和集成测试 → 生成测试报告和覆盖率 → 构建 Docker 镜像 → 推送镜像到仓库 → 部署到目标服务器。

### 代码/配置示例

**GitHub Actions 工作流**（`.github/workflows/ci.yml`）：

```yaml
name: Python CI/CD

# 触发条件：push 到 main/dev 分支，或针对这些分支的 pull request
on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

# 全局环境变量
env:
  PYTHON_VERSION: "3.11"
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ==========================================================
  # Job 1：代码质量检查与测试
  # ==========================================================
  test:
    runs-on: ubuntu-latest

    # 服务化容器：自动启动 PostgreSQL 和 Redis 供测试使用
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      # 1. 检出代码（包含完整 git 历史，便于计算变更范围）
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      # 2. 设置 Python 环境
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: "pip"  # 自动缓存 pip 依赖

      # 3. 安装项目依赖
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      # 4. 代码风格检查（Black 格式化检查，失败时停止）
      - name: Lint with Black
        run: black --check --diff .

      # 5. 静态类型检查
      - name: Type check with mypy
        run: mypy app/

      # 6. 运行测试套件并生成覆盖率报告
      - name: Run tests with pytest
        env:
          DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
        run: pytest --cov=app --cov-report=xml --cov-report=term

      # 7. 上传覆盖率报告到 Codecov（第三方服务，可省略）
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: false

  # ==========================================================
  # Job 2：构建并推送 Docker 镜像（仅在 main 分支 push 时执行）
  # ==========================================================
  build:
    needs: test          # 依赖 test Job 成功后才能执行
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'  # 条件判断

    steps:
      - uses: actions/checkout@v4

      # 1. 登录到 GitHub Container Registry
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # 2. 提取镜像元数据（标签、版本等）
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=,suffix=,format=short
            type=raw,value=latest,enable={{is_default_branch}}

      # 3. 构建并推送镜像（启用 BuildKit 缓存）
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ==========================================================
  # Job 3：部署到生产环境（手动触发 + 环境审批）
  # ==========================================================
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production  # GitHub Environments，可配置审批人

    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/myapp
            docker-compose pull
            docker-compose up -d
            docker system prune -f
```

**GitLab CI 配置**（`.gitlab-ci.yml`）：

```yaml
# 定义执行阶段，按顺序执行
stages:
  - test
  - build
  - deploy

# 全局变量
variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

# 缓存 pip 依赖（cache 在 Job 间共享）
cache:
  paths:
    - .cache/pip/
    - venv/

# 通用配置模板（用 & 定义锚点，* 引用）
.python_base: &python_base
  image: python:3.11-slim
  before_script:
    - python -m venv venv
    - source venv/bin/activate
    - pip install --upgrade pip
    - pip install -r requirements-dev.txt

# ==========================================================
# Stage 1: 测试
# ==========================================================
lint:
  <<: *python_base          # 继承通用模板
  stage: test
  script:
    - black --check .
    - flake8 app/
  only:
    - merge_requests
    - main

test:
  <<: *python_base
  stage: test
  services:
    - postgres:15-alpine
    - redis:7-alpine
  variables:
    POSTGRES_DB: test_db
    POSTGRES_USER: test_user
    POSTGRES_PASSWORD: test_pass
    DATABASE_URL: "postgresql://test_user:test_pass@postgres/test_db"
  script:
    - pytest --cov=app --cov-report=xml
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
  coverage: '/TOTAL.*? (\d{1,3}%)/'

# ==========================================================
# Stage 2: 构建镜像
# ==========================================================
build_image:
  stage: build
  image: docker:24
  services:
    - docker:24-dind          # Docker in Docker
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
  only:
    - main

# ==========================================================
# Stage 3: 部署
# ==========================================================
deploy_prod:
  stage: deploy
  image: alpine:latest
  before_script:
    - apk add --no-cache openssh-client
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -
  script:
    - ssh -o StrictHostKeyChecking=no $DEPLOY_USER@$DEPLOY_HOST "cd /opt/myapp && docker-compose pull && docker-compose up -d"
  environment:
    name: production
    url: https://api.example.com
  only:
    - main
  when: manual                # 手动触发
```

### 常见面试题

#### Q1：CI 和 CD 有什么区别？为什么需要 CI/CD？

**参考答案：** CI（持续集成）关注开发阶段的自动化，核心是频繁合并代码并自动运行构建和测试，目的是尽早发现集成冲突和缺陷。CD 包含两层含义：持续交付（Continuous Delivery）是 CI 通过后自动将代码部署到类生产环境（如预发布），等待人工审批后上生产；持续部署（Continuous Deployment）则更进一步，完全自动化地部署到生产环境。CI/CD 的价值在于缩短反馈周期、降低发布风险、标准化流程、减少人工操作失误。在传统手动部署模式下，发布周期可能以周甚至月计，而 CI/CD 可以将发布频率提升到一天多次，每次变更范围小，出现问题更容易定位和回滚。

#### Q2：GitHub Actions 的 `needs` 关键字有什么作用？如果两个 Job 没有依赖关系，它们会怎样执行？

**参考答案：** `needs` 用于声明 Job 之间的依赖关系，被依赖的 Job 必须成功完成后，当前 Job 才会开始执行。如果多个 Job 之间没有 `needs` 关系，GitHub Actions 会默认**并行执行**它们，这能显著缩短流水线总耗时。例如，可以在一个工作流中并行运行"代码风格检查"、"单元测试"、"安全扫描"，三者互不阻塞。但需要注意，并行的 Job 运行在独立的 runner 上，它们之间默认无法共享文件系统；如果需要传递数据，必须使用 `artifacts` 上传和下载。合理设计 Job 依赖图是优化 CI 流水线执行效率的关键。

---

## 6. 环境变量与配置管理（12-Factor App）

### 概念解释

在软件部署实践中，配置管理是一个容易被忽视但极其关键的话题。**配置**是指随部署环境变化而变化的任何东西，比如数据库连接地址、第三方 API 密钥、日志级别、功能开关等。与之相对的是**代码**，代码在所有环境中应该保持一致。将配置硬编码在源码中是严重的反模式，因为这意味着每个环境都需要维护一个代码分支，极易导致"配置漂移"和生产事故。

**12-Factor App** 是由 Heroku 团队提出的一套云原生应用开发方法论，其中第 III 条原则就是"在环境中存储配置"。它的核心主张是：配置应当严格区分于代码，通过环境变量（Environment Variables）注入到应用中。环境变量是操作系统层面的键值对，不随代码提交到版本控制，因此天然适合存储敏感信息和环境相关配置。

Python 项目中管理环境变量的最佳实践：

1. **`.env` 文件 + `python-dotenv`**：开发环境中将配置写在 `.env` 文件中，应用启动时通过 `python-dotenv` 加载到环境变量。`.env` 文件加入 `.gitignore`，避免提交到仓库。

2. **Pydantic Settings（`pydantic-settings`）**：生产级项目推荐使用 Pydantic 的 `BaseSettings` 类，它能自动从环境变量中读取配置，并进行类型校验和默认值设置，配置错误时会在启动时就报错而不是运行时踩坑。

3. **敏感信息加密**：对于数据库密码、API 密钥等敏感配置，开发环境可以用 `.env`，生产环境应当使用专业的密钥管理服务，如 AWS Secrets Manager、Azure Key Vault、HashiCorp Vault，或 Kubernetes 的 `Sealed Secrets`。

4. **配置分层**：区分不同层级的配置来源，按优先级覆盖。例如：默认值 < `.env` 文件 < 环境变量 < 命令行参数。这样开发环境只需维护 `.env`，生产环境通过容器编排平台注入环境变量。

常见的配置管理反模式包括：将配置写在 Python 常量文件中并提交到 Git、在不同环境使用不同的 Git 分支、在 Dockerfile 中通过 `ENV` 硬编码敏感信息（Docker 镜像可能被推送到公共仓库）。

### 代码/配置示例

**Pydantic Settings 配置类**（`app/config.py`）：

```python
"""
应用配置管理模块
使用 pydantic-settings 实现类型安全的配置加载
支持从环境变量和 .env 文件读取配置
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn, field_validator
from typing import Literal


class Settings(BaseSettings):
    """
    应用配置类
    所有字段自动从环境变量中读取，变量名不区分大小写
    例如：环境变量 APP_ENV → 字段 app_env
    """
    # 加载 .env 文件（仅在开发环境，生产环境直接注入环境变量）
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的额外环境变量
    )

    # ========== 基础配置 ==========
    # 运行环境：development / testing / staging / production
    app_env: Literal["development", "testing", "staging", "production"] = "development"

    # 应用密钥（用于 JWT 签名、Session 加密等，生产环境必须修改）
    secret_key: str = "dev-secret-key-change-in-production"

    # 调试模式（生产环境必须为 False）
    debug: bool = False

    # ========== 数据库配置 ==========
    # PostgreSQL 连接地址，格式：postgresql://user:pass@host:port/db
    database_url: PostgresDsn = "postgresql://user:pass@localhost:5432/myapp"

    # 数据库连接池大小
    db_pool_size: int = 10

    # 数据库连接超时（秒）
    db_pool_timeout: int = 30

    # ========== Redis 配置 ==========
    # Redis 连接地址
    redis_url: RedisDsn = "redis://localhost:6379/0"

    # ========== 日志配置 ==========
    # 日志级别
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # 日志格式：json（生产环境，便于日志系统解析）或 text（开发环境）
    log_format: Literal["json", "text"] = "text"

    # ========== 第三方服务配置 ==========
    # 阿里云 OSS 配置
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket_name: str = ""
    oss_endpoint: str = ""

    # 短信服务 API Key
    sms_api_key: str = ""

    # ========== 功能开关 ==========
    # 是否启用用户注册（可用于临时关闭注册应对攻击）
    enable_registration: bool = True

    # 是否启用邮件通知
    enable_email_notification: bool = True

    # ========== 校验器 ==========
    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """生产环境检查密钥是否为默认值"""
        if info.data.get("app_env") == "production" and v == "dev-secret-key-change-in-production":
            raise ValueError("生产环境的 SECRET_KEY 不能使用默认值！")
        return v

    @field_validator("debug")
    @classmethod
    def validate_debug(cls, v: bool, info) -> bool:
        """生产环境禁止开启调试模式"""
        if info.data.get("app_env") == "production" and v is True:
            raise ValueError("生产环境不能开启 DEBUG 模式！")
        return v


# 全局配置实例（应用启动时只实例化一次）
settings = Settings()

# 使用示例：
# from app.config import settings
# db_url = settings.database_url
# if settings.app_env == "production": ...
```

**`.env` 文件示例**（开发环境，加入 `.gitignore`）：

```bash
# 应用基础配置
APP_ENV=development
DEBUG=true
SECRET_KEY=dev-only-secret-do-not-use-in-production

# 数据库配置
DATABASE_URL=postgresql://devuser:devpass@localhost:5432/myapp_dev
DB_POOL_SIZE=5

# Redis 配置
REDIS_URL=redis://localhost:6379/1

# 日志配置
LOG_LEVEL=DEBUG
LOG_FORMAT=text

# 功能开关
ENABLE_REGISTRATION=true
```

**Docker Compose 环境变量注入**（`docker-compose.yml` 片段）：

```yaml
services:
  web:
    env_file:
      - .env
    environment:
      # 覆盖 .env 中的配置（优先级更高）
      - APP_ENV=production
      - DEBUG=false
      # 从宿主机环境变量读取敏感信息，不写入任何文件
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=${DATABASE_URL}
      - SMS_API_KEY=${SMS_API_KEY}
```

### 常见面试题

#### Q1：12-Factor App 的配置原则是什么？为什么不应该把配置写在代码里？

**参考答案：** 12-Factor App 的第三条原则是"在环境中存储配置"，主张将配置与代码严格分离，通过环境变量注入。不应该把配置写在代码里的原因有三：（1）**安全性**：代码通常会提交到版本控制（如 Git），硬编码的密码和密钥会被所有有代码访问权限的人看到，存在严重的泄露风险；（2）**灵活性**：不同环境（开发、测试、生产）需要不同的配置，如果写在代码里，每个环境都要维护独立的分支，极易导致配置不一致和合并冲突；（3）**可移植性**：配置与代码耦合会导致应用无法在不修改源码的情况下部署到新环境，违背了"一次构建，到处运行"的容器化理念。环境变量是操作系统级的基础设施，所有编程语言和部署平台都支持，是最通用的配置传递方式。

#### Q2：生产环境中如何安全地管理数据库密码等敏感配置？

**参考答案：** 生产环境管理敏感配置应采用分层策略：（1）**绝不写入代码或镜像**：数据库密码、API 密钥等绝不能出现在 Git 仓库、Dockerfile 或 Docker 镜像层中；（2）**使用专业密钥管理服务**：如 AWS Secrets Manager、HashiCorp Vault、Kubernetes Secrets，这些服务提供加密存储、访问审计、自动轮转等功能；（3）**运行时注入**：应用在启动时从密钥服务读取配置，或者由容器编排平台（K8s、Docker Compose）将环境变量注入容器；（4）**最小权限原则**：每个服务只获取其必需的密钥，限制密钥的读取权限；（5）**定期轮转**：设置密码和密钥的有效期，到期自动更新。对于中小规模项目，如果暂时无法引入 Vault 等重型方案，至少应做到：`.env` 文件加入 `.gitignore`、生产环境通过 CI/CD 流水线的 Secrets 功能注入变量、定期更换密钥。

---

## 7. 日志轮转与系统监控

### 概念解释

在生产环境中，日志和监控是运维的"双眼"——没有它们，系统就像黑盒，故障排查只能靠猜。Python 应用会产生大量日志，如果不对日志进行管理，磁盘很快会被填满，导致服务崩溃。同样，没有监控的系统，在故障发生时无法第一时间感知，用户体验受损后才被动发现。

**日志轮转（Log Rotation）** 是指当日志文件达到一定大小或时间后，自动将其归档、压缩，并创建新的日志文件继续写入。Linux 系统上最常用的日志轮转工具是 `logrotate`，它是系统自带的守护进程，通过 `/etc/logrotate.d/` 下的配置文件管理各个应用的日志。Python 的 `logging` 模块也内置了 `RotatingFileHandler` 和 `TimedRotatingFileHandler`，可以在应用层实现轮转，但生产环境更推荐统一使用 `logrotate`，因为它更可靠（应用崩溃不影响日志文件操作），且能执行压缩和清理等后处理。

**系统监控**分为三个层面：

1. **基础设施监控**：CPU、内存、磁盘 I/O、网络流量、系统负载（load average）等。常用工具：`top`、`htop`、`vmstat`、`iostat`、`sar`、`netstat`，以及可视化方案 Prometheus + Grafana。

2. **应用监控（APM）**：请求延迟、错误率、吞吐量、数据库查询耗时、外部 API 调用耗时等。Python 生态中常用 Sentry（错误追踪）、Prometheus 客户端库（`prometheus_client`）、StatsD + Grafana。

3. **日志聚合**：将分散在多台服务器上的日志集中收集到一处，便于搜索和分析。常用方案：ELK 栈（Elasticsearch + Logstash + Kibana）、EFK 栈（用 Fluentd 替代 Logstash）、Loki + Grafana。

对于 Python 后端服务，监控的关键指标（俗称"黄金信号"）包括：延迟（Latency）、流量（Traffic）、错误（Errors）、饱和度（Saturation）。Prometheus 的 `RED` 方法（Rate、Errors、Duration）和 `USE` 方法（Utilization、Saturation、Errors）是设计监控指标的经典框架。

### 代码/配置示例

**Python 日志配置**（使用 `logging` 模块 + JSON 格式，便于日志系统解析）：

```python
"""
生产级日志配置模块
输出 JSON 格式日志，便于 ELK/Loki 等日志系统解析
同时输出到控制台和文件，文件按大小自动轮转
"""

import logging
import logging.handlers
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """自定义 JSON 格式日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pathname": record.pathname,
            "lineno": record.lineno,
            "funcName": record.funcName,
        }
        # 如果有异常信息，加入堆栈跟踪
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        # 如果有 extra 字段，合并进来
        for key, value in record.__dict__.items():
            if key not in log_obj and not key.startswith("_"):
                log_obj[key] = value
        return json.dumps(log_obj, ensure_ascii=False, default=str)


def setup_logging(
    app_name: str = "myapp",
    log_level: str = "INFO",
    log_dir: str = "/var/log/myapp",
    enable_json: bool = True,
) -> logging.Logger:
    """配置应用日志

    Args:
        app_name: 应用名称，用于日志标识
        log_level: 日志级别，DEBUG/INFO/WARNING/ERROR/CRITICAL
        log_dir: 日志文件目录
        enable_json: 是否输出 JSON 格式（生产环境建议 True）
    """
    logger = logging.getLogger(app_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # 避免重复添加 handler（多次调用 setup_logging 时）
    if logger.handlers:
        return logger

    # 选择格式化器
    if enable_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s "
            "(%(pathname)s:%(lineno)d)"
        )

    # 1. 控制台 Handler（标准错误输出）
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. 文件 Handler（按大小轮转，单个文件 10MB，保留 10 个备份）
    # 注意：生产环境更推荐配合系统级 logrotate 使用
    file_handler = logging.handlers.RotatingFileHandler(
        filename=f"{log_dir}/app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,              # 保留 10 个备份文件
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 3. 错误日志单独输出到 error.log（只记录 ERROR 及以上）
    error_handler = logging.handlers.RotatingFileHandler(
        filename=f"{log_dir}/error.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


# 使用示例
# logger = setup_logging(app_name="myapp", log_level="INFO", enable_json=True)
# logger.info("用户登录成功", extra={"user_id": 123, "ip": "192.168.1.1"})
# logger.error("数据库连接失败", exc_info=True, extra={"db_host": "localhost"})
```

**logrotate 配置**（`/etc/logrotate.d/myapp`）：

```bash
# myapp 应用日志轮转配置
# logrotate 每天运行一次（由系统 cron 触发），自动匹配符合条件的日志

/var/log/myapp/*.log {
    # 每天轮转一次
    daily

    # 日志文件达到 50MB 时也触发轮转（与 daily 是"或"关系）
    size 50M

    # 保留 30 天的日志备份
    rotate 30

    # 轮转后创建新的空日志文件
    create 0644 appuser appgroup

    # 对旧日志进行 gzip 压缩
    compress

    # 压缩延迟到下一次轮转（避免刚轮转就压缩影响性能）
    delaycompress

    # 如果日志文件不存在，不报错
    missingok

    # 如果日志文件为空，不轮转
    notifempty

    # 多个匹配文件时，分别轮转而不是合并
    sharedscripts

    # 轮转后执行的脚本：通知应用重新打开日志文件
    postrotate
        # 向 Gunicorn 主进程发送 USR1 信号，触发日志重新打开
        # 避免应用继续向已重命名的旧文件写入
        kill -USR1 $(cat /run/myapp.pid) > /dev/null 2>&1 || true
    endscript
}
```

**Prometheus 指标暴露**（Python 应用集成示例）：

```python
"""
使用 prometheus_client 暴露应用监控指标
配合 Prometheus 抓取 + Grafana 可视化
"""

from prometheus_client import Counter, Histogram, Info, generate_latest, CONTENT_TYPE_LATEST
from flask import Flask, Response
import time

app = Flask(__name__)

# 1. 计数器：统计 HTTP 请求总数（按方法和状态码分类）
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

# 2. 直方图：统计请求处理耗时（Prometheus 自动计算分位数）
http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# 3. 信息指标：记录应用版本
app_info = Info("app_info", "Application information")
app_info.info({"version": "1.2.3", "environment": "production"})


@app.before_request
def before_request():
    """请求开始时记录时间"""
    flask.g.start_time = time.time()


@app.after_request
def after_request(response):
    """请求结束后记录指标"""
    if hasattr(flask.g, "start_time"):
        duration = time.time() - flask.g.start_time
        method = request.method
        endpoint = request.endpoint or "unknown"
        status = str(response.status_code)

        # 记录请求总数
        http_requests_total.labels(
            method=method, endpoint=endpoint, status_code=status
        ).inc()

        # 记录请求耗时
        http_request_duration.labels(
            method=method, endpoint=endpoint
        ).observe(duration)

    return response


@app.route("/metrics")
def metrics():
    """Prometheus 抓取端点"""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/health")
def health():
    """健康检查端点"""
    return {"status": "healthy"}
```

**常用系统监控命令速查**：

```bash
# ========== CPU 与进程 ==========
# 实时查看进程和资源占用（交互式，按 M 按内存排序，按 P 按 CPU 排序）
top

# top 的增强版，支持彩色显示和鼠标操作
htop

# 查看系统整体负载（1分钟、5分钟、15分钟平均负载）
uptime

# 每 2 秒采样一次 CPU 统计，共采样 5 次
vmstat 2 5

# ========== 内存 ==========
# 查看内存使用情况（-h 人类可读）
free -h

# 按内存占用排序查看进程
ps aux --sort=-%mem | head -n 10

# ========== 磁盘 ==========
# 查看磁盘空间使用情况
df -h

# 查看目录占用空间大小
du -sh /var/log/myapp

# 实时监控磁盘 I/O
iostat -x 2

# ========== 网络 ==========
# 查看网络连接和监听端口（-t: TCP, -l: 监听, -n: 数字显示, -p: 显示进程）
ss -tlnp

# 查看网络流量统计（需安装 iftop 或 nethogs）
sudo iftop -i eth0

# 抓包分析（-i 指定网卡，port 指定端口）
sudo tcpdump -i eth0 port 8080 -w capture.pcap

# ========== 系统综合 ==========
# 综合系统活动报告（CPU、内存、IO、网络）
sar -u -r -d 2 5
```

### 常见面试题

#### Q1：`logrotate` 的 `copytruncate` 和 `create` 有什么区别？什么时候应该用哪个？

**参考答案：** `create` 是 logrotate 的默认行为：先重命名旧日志文件（如 `app.log` → `app.log.1`），然后创建新的空日志文件（`app.log`）。但这种方式需要应用支持重新打开日志文件（如 Gunicorn 收到 `USR1` 信号后会重新打开），否则应用会继续向已重命名的旧文件写入。`copytruncate` 则是先复制旧日志内容到备份文件，然后清空原日志文件。它的优点是不需要通知应用，任何程序都能配合；缺点是在复制和截断之间有一个时间窗口，可能会丢失少量日志，且对正在写入的大日志文件性能开销较大。选择建议：如果应用支持信号通知重新打开日志（如 Nginx、Gunicorn、Python 的 `WatchedFileHandler`），用 `create` + `postrotate` 脚本；如果应用不支持或你无法修改应用行为，用 `copytruncate`。

#### Q2：Prometheus 的 Counter、Gauge、Histogram 和 Summary 四种指标类型有什么区别？

**参考答案：** Prometheus 定义了四种核心指标类型，适用于不同的监控场景：（1）**Counter（计数器）**：只增不减的累计值，适合统计请求总数、错误总数、处理任务数等。必须使用 `.inc()` 或 `.labels(...).inc()` 来增加，不能减。如果进程重启，计数器归零，Prometheus 的 `rate()` 函数能正确处理这种重置。（2）**Gauge（仪表盘）**：可增可减的瞬时值，适合监控当前温度、内存使用量、队列长度、在线用户数等。使用 `.set()`、`.inc()`、`.dec()` 修改。（3）**Histogram（直方图）**：对观测值进行分桶（bucket）统计，适合请求延迟、响应大小等分布型数据。它会自动计算每个桶的累计计数，配合 `histogram_quantile()` 函数可以计算任意分位数（如 P99 延迟）。需要预先定义桶的边界。（4）**Summary（摘要）**：与 Histogram 类似也用于分布型数据，但它直接在客户端计算分位数（如中位数、99 分位数），通过网络传输的量更小，但无法在服务端聚合多个实例的数据。因此微服务架构中更推荐用 Histogram，因为它支持跨实例聚合计算全局分位数。

---

> **本章小结**：Linux 与部署运维是后端开发的"最后一公里"。从 Linux 命令行到 systemd 进程守护，从 Nginx 反向代理到 Docker 容器化，从 CI/CD 自动化到 12-Factor 配置管理，再到日志轮转与监控告警——这些知识串联起来，构成了完整的服务部署与运维体系。面试中不仅要能答出"是什么"，更要能结合项目经验讲出"为什么选这个方案"和"遇到什么问题怎么解决的"，这才是区分初级与高级开发者的关键。




---


# 第 7 章：项目

> 面试中"项目经验"类问题是区分"会写代码"和"能做好工程"的核心分水岭。本章从架构设计、代码规范、文档管理、测试体系、性能调优到面试应答策略，系统梳理 Python 全栈项目落地的核心知识。

---

## 项目结构设计

### 为什么项目结构如此重要？

好的项目结构就像一栋建筑的地基和框架——它决定了系统的可扩展性、可维护性和团队协作效率。一个没有良好结构的 Python 项目，随着业务发展，会迅速变成"意大利面条式代码"（Spaghetti Code），新成员需要数周才能理解，修改一个需求可能引发连锁崩溃。

在实际工作中，我们面对的是不断演进的业务需求。今天的内部工具可能是明天的核心系统，今天的单体应用可能需要拆分为微服务。如果项目结构从一开始就没有清晰的边界和分层，重构的成本将呈指数级增长。

### 分层架构（Layered Architecture）

分层架构是最经典、最易落地的架构模式，它将系统按照职责划分为不同的层级，每一层只依赖于其下方的层。

典型的三层架构：

```python
my_project/
├── api/                    # 表示层（Presentation Layer）
│   ├── __init__.py
│   ├── routes/             # 路由定义
│   │   ├── __init__.py
│   │   ├── user_routes.py  # 用户相关接口
│   │   └── order_routes.py # 订单相关接口
│   └── schemas/            # Pydantic 请求/响应模型
│       ├── __init__.py
│       └── user_schemas.py
├── services/               # 业务逻辑层（Business Logic Layer）
│   ├── __init__.py
│   ├── user_service.py     # 用户业务逻辑
│   └── order_service.py    # 订单业务逻辑
├── repositories/           # 数据访问层（Data Access Layer）
│   ├── __init__.py
│   ├── base_repo.py        # 基础仓储抽象
│   ├── user_repo.py        # 用户数据操作
│   └── order_repo.py       # 订单数据操作
├── models/                 # ORM 模型定义
│   ├── __init__.py
│   └── database.py         # 数据库连接和基类
├── core/                   # 核心配置和工具
│   ├── __init__.py
│   ├── config.py           # 环境配置
│   ├── exceptions.py       # 自定义异常
│   └── dependencies.py     # 依赖注入
└── main.py                 # 应用入口
```

**分层架构的核心原则：**

1. **单向依赖**：上层可以调用下层，下层绝不可反向依赖上层。这保证了核心逻辑不受表示层变化的影响。
2. **每层只关心自己的事**：API 层负责 HTTP 协议、序列化；Service 层负责业务规则编排；Repository 层负责数据持久化。
3. **通过接口解耦**：Service 层不应该直接实例化 Repository，而应该通过依赖注入获取接口实例。

```python
# 业务逻辑层示例：不依赖具体的数据库实现
from abc import ABC, abstractmethod
from typing import List
from api.schemas.user_schemas import UserCreate, UserResponse

# 定义仓储接口（抽象）
class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> UserResponse | None:
        """根据 ID 获取用户"""
        pass
    
    @abstractmethod
    async def create(self, user: UserCreate) -> UserResponse:
        """创建用户"""
        pass

# 业务服务层：只依赖接口，不关心底层实现
class UserService:
    def __init__(self, repo: IUserRepository):
        # 通过构造函数注入依赖，方便测试时替换为 Mock
        self._repo = repo
    
    async def register_user(self, user_data: UserCreate) -> UserResponse:
        """用户注册业务逻辑"""
        # 业务规则校验
        if len(user_data.password) < 8:
            raise ValueError("密码长度不能少于 8 位")
        
        # 调用仓储层持久化
        return await self._repo.create(user_data)
```

### Clean Architecture（整洁架构）

Robert C. Martin 提出的 Clean Architecture 是分层架构的进阶版，核心思想是**依赖规则**：内层的代码不依赖外层，只有外层的代码可以依赖内层。

```
┌─────────────────────────────────────┐
│  框架与驱动层（Frameworks & Drivers）   │  ← FastAPI、SQLAlchemy、Redis
│  ┌───────────────────────────────┐  │
│  │  接口适配器层（Interface       │  │  ← 控制器、 presenters、视图模型
│  │   Adapters）                  │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │  应用业务规则层（Use      │  │  │  ← 用例编排、服务协调
│  │  │   Cases）                │  │  │
│  │  │  ┌───────────────────┐  │  │  │
│  │  │  │  企业业务规则层    │  │  │  │  ← 实体（Entity）、领域对象
│  │  │  │  （Enterprise      │  │  │  │
│  │  │  │   Business Rules） │  │  │  │
│  │  │  └───────────────────┘  │  │  │
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

在 Python 中的实践：

```python
# domain/entities.py —— 最内层，不依赖任何外部框架
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Order:
    """订单领域实体：核心业务规则的载体"""
    id: Optional[int]
    user_id: int
    items: list
    total_amount: float
    status: str  # pending / paid / shipped / completed
    created_at: Optional[datetime] = None
    
    def calculate_total(self) -> float:
        """计算订单总金额（业务规则）"""
        return sum(item.price * item.quantity for item in self.items)
    
    def can_cancel(self) -> bool:
        """判断订单是否可以取消（业务规则）"""
        return self.status in ("pending", "paid")


# use_cases/order_use_case.py —— 用例层，编排业务流程
from domain.entities import Order
from domain.repositories import IOrderRepository
from domain.services import IPaymentService

class CreateOrderUseCase:
    """创建订单用例：协调多个领域服务完成一个完整的业务操作"""
    
    def __init__(
        self,
        order_repo: IOrderRepository,
        payment_service: IPaymentService
    ):
        self.order_repo = order_repo
        self.payment_service = payment_service
    
    async def execute(self, user_id: int, items: list) -> Order:
        # 1. 创建订单实体
        order = Order(
            id=None,
            user_id=user_id,
            items=items,
            total_amount=0,
            status="pending"
        )
        order.total_amount = order.calculate_total()
        
        # 2. 持久化订单
        saved_order = await self.order_repo.save(order)
        
        # 3. 调用支付服务创建预支付订单
        await self.payment_service.create_payment(saved_order)
        
        return saved_order
```

**Clean Architecture 的优势：**
- **框架无关**：可以替换 FastAPI 为 Flask，不影响核心业务
- **UI 无关**：Web 界面和 CLI 可以共用同一套业务逻辑
- **数据库无关**：可以从 PostgreSQL 切换到 MongoDB，只需改动 Repository 实现
- **高度可测试**：内层代码不依赖外部基础设施，单元测试无需启动数据库

### 领域驱动设计（DDD）基础

DDD 是处理复杂业务领域的架构方法论。其核心思想是通过建立统一的**领域模型**，让技术术语与业务术语对齐。

DDD 中的核心概念：

| 概念 | 说明 | Python 实践 |
|------|------|-------------|
| **实体（Entity）** | 有唯一标识的对象，即使属性变化也仍是同一个 | 带有 `id` 的 dataclass |
| **值对象（Value Object）** | 没有唯一标识，由属性值定义的对象 | 不可变的 dataclass（`frozen=True`） |
| **聚合（Aggregate）** | 一组相关对象的集合，以聚合根为统一入口 | 聚合根实体 + 相关实体/值对象 |
| **仓储（Repository）** | 聚合的持久化抽象，屏蔽数据访问细节 | 抽象基类 + 具体实现 |
| **领域服务（Domain Service）** | 不适合放在实体中的跨实体业务逻辑 | 独立的 service 类 |

```python
from dataclasses import dataclass, field
from typing import List
from uuid import UUID, uuid4

# 值对象：Address
@dataclass(frozen=True)  # 不可变，创建后不能修改
class Address:
    """地址值对象：两个地址的属性相同则视为相等"""
    province: str
    city: str
    district: str
    detail: str

# 实体：OrderItem
@dataclass
class OrderItem:
    """订单项：有唯一标识的实体"""
    id: UUID = field(default_factory=uuid4)
    product_id: int = 0
    product_name: str = ""
    price: float = 0.0
    quantity: int = 0
    
    @property
    def subtotal(self) -> float:
        return self.price * self.quantity

# 聚合根：Order（聚合根）
class OrderAggregate:
    """
    订单聚合：Order 是聚合根
    所有对 OrderItem 的操作都必须通过 Order 进行
    """
    def __init__(self, order_id: UUID, user_id: int):
        self._id = order_id
        self._user_id = user_id
        self._items: List[OrderItem] = []
        self._shipping_address: Address | None = None
        self._status = "created"
    
    @property
    def id(self) -> UUID:
        return self._id
    
    def add_item(self, item: OrderItem) -> None:
        """添加商品项（聚合根管理内部实体）"""
        # 业务规则校验
        if self._status != "created":
            raise ValueError("只能向未提交的订单添加商品")
        if item.quantity <= 0:
            raise ValueError("商品数量必须大于 0")
        self._items.append(item)
    
    def set_shipping_address(self, address: Address) -> None:
        """设置收货地址"""
        self._shipping_address = address
    
    @property
    def total_amount(self) -> float:
        return sum(item.subtotal for item in self._items)
    
    def submit(self) -> None:
        """提交订单：状态机转换"""
        if not self._items:
            raise ValueError("订单不能为空")
        if self._shipping_address is None:
            raise ValueError("请设置收货地址")
        self._status = "submitted"
```

**DDD 的适用场景：**
- ✅ 业务逻辑复杂、规则多变（如电商、金融、供应链）
- ✅ 团队规模较大，需要统一业务语言
- ❌ 简单的 CRUD 应用或原型项目（过度设计）

### 常见面试题

#### 面试题 1：分层架构中，如果 Service 层需要返回给前端一个特定的数据格式，应该在哪一层做数据转换？

**参考答案：**

数据转换应该在**接口层（API/Presentation Layer）**完成，而不是在 Service 层。

Service 层应该返回领域对象或通用的数据结构（如 dict），保持与表示层的解耦。接口层使用 Schema（如 Pydantic 模型）将 Service 层返回的数据转换为前端需要的格式。

```python
# 错误做法：Service 层耦合了 HTTP 响应格式
class UserService:
    async def get_user(self, user_id: int) -> dict:
        user = await self.repo.get(user_id)
        return {
            "code": 200,          # ❌ 不应该在 Service 层处理 HTTP 状态码
            "data": {             # ❌ 不应该在 Service 层处理响应包装
                "id": user.id,
                "name": user.name
            }
        }

# 正确做法：Service 层只返回领域对象
class UserService:
    async def get_user(self, user_id: int) -> User:
        return await self.repo.get(user_id)

# API 层负责序列化和响应包装
@router.get("/users/{user_id}")
async def get_user(user_id: int, service: UserService = Depends()):
    user = await service.get_user(user_id)
    return {"code": 200, "data": UserResponse.from_orm(user)}  # ✅
```

#### 面试题 2：什么时候应该选择 Clean Architecture，什么时候简单的三层架构就够了？

**参考答案：**

选择架构的核心依据是**业务复杂度**和**项目生命周期**：

| 维度 | 三层架构 | Clean Architecture |
|------|----------|-------------------|
| 业务复杂度 | 简单到中等 | 复杂 |
| 项目生命周期 | 短期或中期 | 长期演进 |
| 团队规模 | 小团队（1-3 人） | 中大型团队 |
| 技术栈稳定性 | 技术栈确定 | 可能替换框架/数据库 |
| 测试要求 | 基础测试 | 严格的单元测试覆盖率 |

**实际建议：**
1. **MVP 阶段**：用三层架构快速验证业务，不要过度设计
2. **成长期**：引入接口抽象（Repository 模式），为后续拆分做准备
3. **成熟期**：核心业务模块采用 Clean Architecture，非核心模块保持简单

从工程实践角度，"渐进式架构"是最好的策略——根据业务复杂度的增长逐步引入更严格的架构约束，而不是一开始就追求完美的架构。

---

## 代码规范

### 为什么代码规范是工程化的基石？

代码规范不是"洁癖"，而是**团队协作的基础设施**。在真实的商业项目中：
- 一个功能模块可能由多个人在数月内接力开发
- 代码审查（Code Review）是发现缺陷的最有效手段
- 规范的代码能将认知负荷降到最低，让开发者聚焦于业务逻辑本身

根据《Clean Code》中的观点，"代码被阅读的次数远多于被编写的次数"。不规范的代码会导致：
- 新成员上手周期变长
- Bug 定位时间增加（因为难以快速理解代码意图）
- 重构风险增加（不清楚改动会影响哪些地方）
- 技术债务累积，最终拖垮迭代速度

### PEP 8 —— Python 代码风格指南

PEP 8 是 Python 官方的代码风格指南，涵盖命名约定、代码布局、注释规范等。以下是面试和生产中最常涉及的要点：

**命名规范：**

```python
# 模块名：小写，可用下划线分隔
# my_module.py ✓    mymodule.py ✓    MyModule.py ✗

# 类名：驼峰命名法（CapWords）
class UserAccountManager:  # ✅
    pass

class user_account_manager:  # ❌
    pass

# 函数名和变量名：小写，下划线分隔

def calculate_order_total(items):  # ✅
    pass

def CalculateOrderTotal(items):  # ❌ 这是类名的命名方式
    pass

# 常量：全大写，下划线分隔
MAX_RETRY_COUNT = 3  # ✅
max_retry_count = 3   # ❌ 容易与变量混淆

# 私有属性/方法：单下划线前缀
class UserService:
    def __init__(self):
        self._cache = {}  # 模块内部使用的属性
    
    def _validate_input(self, data):  # 模块内部使用的方法
        pass

# 强私有（避免名称冲突）：双下划线前缀（触发名称改写）
class PaymentGateway:
    def __init__(self):
        self.__api_key = "secret"  # 会被改写为 _PaymentGateway__api_key
```

**代码布局：**

```python
# 缩进：4 个空格（绝对不能混用 Tab 和空格）
def process_data(data):
    result = []
    for item in data:
        if item.is_valid():
            result.append(item)
    return result

# 行长度：最大 79/88 字符（Black 默认 88）
# 长表达式换行：使用括号隐式续行
total_price = (
    base_price
    + tax_amount
    - discount_amount
    + shipping_fee
)

# 空行：顶级函数和类之间用 2 行空行，类内方法之间用 1 行空行
class OrderProcessor:
    """订单处理器"""
    
    def __init__(self, repository):
        self._repo = repository
    
    def process(self, order):
        """处理单个订单"""
        validated = self._validate(order)
        return self._repo.save(validated)
    
    def batch_process(self, orders):
        """批量处理订单"""
        return [self.process(o) for o in orders]


class PaymentProcessor:
    """支付处理器"""
    pass


# 导入排序：标准库 > 第三方库 > 本地模块，每组之间空一行
import os
import sys
from datetime import datetime

import requests
from fastapi import FastAPI
from sqlalchemy.orm import Session

from my_project.core.config import settings
from my_project.services.user_service import UserService
```

### Black —— 不妥协的代码格式化工具

Black 被称为"不妥协的 Python 代码格式化工具"，它的哲学是**消除关于代码风格的争论**——配置选项极少，所有人使用相同的规则。

```bash
# 安装
pip install black

# 格式化单个文件
black my_script.py

# 格式化整个项目
black .

# 检查是否有文件需要格式化（CI 中使用）
black --check .

# 显示将要做的更改但不实际执行（dry-run）
black --diff .
```

**Black 的核心特性：**

1. **极少的配置项**：没有 `line-length: 80 or 120?` 的争论，默认 88 字符，可通过 `-l` 调整
2. **确定性输出**：同样的输入永远产生同样的输出，确保团队一致性
3. **速度足够快**：即使是大型项目也能在数秒内完成格式化

```python
# Black 格式化前（多种风格混合）
def foo( x,y ):
    if x==1:
        return y+1
    elif x==2:
        return y*2
    else:
        return y

# Black 格式化后（统一风格）
def foo(x, y):
    if x == 1:
        return y + 1
    elif x == 2:
        return y * 2
    else:
        return y
```

**Black 的配置（pyproject.toml）：**

```toml
[tool.black]
line-length = 88          # 行长度
target-version = ["py39"] # 目标 Python 版本（影响语法特性）
include = '\.pyi?$'       # 包含的文件模式
exclude = '''
/(
    \.git
  | \.venv
  | build
  | dist
)/
'''
```

### Ruff —— 极速的 Python 代码检查工具

Ruff 是一个用 Rust 编写的 Python 代码检查工具（Linter），它的速度比 flake8 + isort + pydocstyle 的组合快 10-100 倍，同时几乎覆盖了它们的所有规则。

```bash
# 安装
pip install ruff

# 检查代码（相当于 flake8 + 更多）
ruff check .

# 自动修复可修复的问题
ruff check . --fix

# 检查并格式化导入排序（替代 isort）
ruff check . --select I

# Ruff 也包含格式化功能（替代 Black）
ruff format .
```

**Ruff 的优势：**
- **速度极快**：10 万行代码的检查仅需毫秒级
- **规则全面**：原生支持 500+ 条规则（Pyflakes、Flake8、isort、pydocstyle 等）
- **兼容 Black**：格式化输出与 Black 一致
- **统一工具链**：一个工具替代多个工具，减少依赖管理复杂度

```toml
# pyproject.toml 中的 Ruff 配置
[tool.ruff]
# 目标 Python 版本
target-version = "py39"

# 启用的规则集
select = [
    "E",   # pycodestyle 错误
    "F",   # Pyflakes
    "I",   # isort（导入排序）
    "N",   # pep8-naming（命名规范）
    "W",   # pycodestyle 警告
    "UP",  # pyupgrade（升级语法）
    "B",   # flake8-bugbear（常见 Bug 模式）
    "C4",  # flake8-comprehensions（推导式优化）
]

# 忽略的规则
ignore = ["E501"]  # 行长度由 Black/formatter 处理

[tool.ruff.pydocstyle]
convention = "google"  # 文档字符串风格

[tool.ruff.isort]
known-first-party = ["my_project"]  # 本地模块名称
```

### pre-commit —— 代码提交前的自动化检查

pre-commit 是一个 Git 钩子框架，可以在代码提交前自动运行检查工具，确保只有符合规范的代码才能进入仓库。

```bash
# 安装
pip install pre-commit

# 安装 Git 钩子（只需执行一次）
pre-commit install

# 手动运行所有钩子（不提交代码）
pre-commit run --all-files

# 运行单个钩子
pre-commit run black --all-files
```

**`.pre-commit-config.yaml` 配置示例：**

```yaml
# 文件位置：项目根目录 .pre-commit-config.yaml
repos:
  # Ruff：代码检查和自动修复
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # MyPy：静态类型检查
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]

  # 通用检查
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace      # 去除行尾空格
      - id: end-of-file-fixer        # 确保文件以空行结尾
      - id: check-yaml               # YAML 语法检查
      - id: check-json               # JSON 语法检查
      - id: check-merge-conflict     # 检查是否有未解决的合并冲突标记
      - id: debug-statements         # 禁止提交 print/debug 语句
```

**pre-commit 的工作流程：**

```
开发者执行 git commit
       ↓
Git 触发 pre-commit 钩子
       ↓
Ruff 检查并自动修复代码风格
       ↓
检查通过？ ── 否 ──→ 阻止提交，显示错误
       ↓ 是
MyPy 进行类型检查
       ↓
检查通过？ ── 否 ──→ 阻止提交
       ↓ 是
通用检查（trailing-whitespace 等）
       ↓
所有检查通过 → 允许提交
```

### 常见面试题

#### 面试题 1：Black 格式化后会修改代码的 AST 吗？如果团队里有人不用 Black，会产生什么问题？

**参考答案：**

Black 承诺**不会改变代码的 AST（抽象语法树）**，这意味着格式化前后的代码在语义上是完全等价的。唯一的例外是某些魔法注释（如 `# fmt: off`）保护的代码块。

如果团队部分成员不用 Black，会产生以下问题：

1. **无意义的 Diff**：A 用 Black 格式化后提交，B 修改同一文件后未格式化，再次提交时会引入大量风格变更的 Diff，淹没真正的业务变更，极大增加 Code Review 难度
2. **合并冲突**：风格差异会增加不必要的合并冲突
3. **CI 失败**：如果 CI 配置了 Black 检查，未格式化的代码会导致构建失败

**解决方案：**
- 强制所有人安装 pre-commit 钩子
- CI 中运行 `black --check` 确保入仓代码已格式化
- 在 IDE 中配置保存时自动格式化（VS Code 的 Black Formatter 插件、PyCharm 的 File Watchers）

#### 面试题 2：在 CI/CD 流水线中，代码规范检查应该放在哪个阶段？

**参考答案：**

代码规范检查应该放在**构建阶段的最前面**，作为"快速失败"（fail-fast）的关卡。

典型的流水线顺序：

```
1. Lint / Format Check（Ruff/Black） ← 最快，几秒完成
2. Type Check（MyPy）                  ← 较快，几十秒
3. Unit Test（pytest）                 ← 中等，1-5 分钟
4. Integration Test                    ← 较慢，5-10 分钟
5. Build & Deploy                      ← 最慢
```

**原因：**
- Lint 检查最快，如果失败可以立即反馈，不浪费后续更耗时的测试资源
- 风格问题应该在提交前就被 pre-commit 拦截，进入 CI 已经是"二次防线"
- 将快检查和慢检查分开，开发者不用等 10 分钟才发现少了一个空格

---

## 接口文档与版本管理

### API 文档的重要性

在前后端分离的架构中，API 文档是团队之间最重要的"契约"。好的 API 文档不仅仅是参数列表，还应该包含：
- 接口的业务语义和使用场景
- 错误码和对应的处理建议
- 请求/响应的完整示例
- 权限要求
- 限流策略

没有文档的 API 就像没有说明书的工具——能用，但充满了猜测和试错成本。

### OpenAPI/Swagger 自动生成文档

FastAPI 最大的优势之一就是原生支持基于类型注解自动生成 OpenAPI 文档。

```python
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

app = FastAPI(
    title="电商 API",
    description="全栈八股文示例项目 API 文档",
    version="1.0.0",
    docs_url="/docs",      # Swagger UI 路径
    redoc_url="/redoc",    # ReDoc 路径
)

# 使用 Pydantic 模型定义请求/响应结构，自动生成文档
class ProductCategory(str, Enum):
    """商品分类枚举"""
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    FOOD = "food"

class ProductCreate(BaseModel):
    """创建商品的请求模型"""
    name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    price: float = Field(..., gt=0, description="商品价格，必须大于 0")
    category: ProductCategory = Field(..., description="商品分类")
    stock: int = Field(default=0, ge=0, description="库存数量")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "iPhone 15",
                "price": 5999.00,
                "category": "electronics",
                "stock": 100
            }
        }

class ProductResponse(BaseModel):
    """商品响应模型"""
    id: int = Field(..., description="商品 ID")
    name: str = Field(..., description="商品名称")
    price: float = Field(..., description="商品价格")
    category: str = Field(..., description="商品分类")
    stock: int = Field(..., description="库存数量")
    created_at: str = Field(..., description="创建时间 ISO 格式")

@app.post(
    "/api/v1/products",
    response_model=ProductResponse,
    status_code=201,
    summary="创建商品",
    description="创建一个新的商品，需要管理员权限",
    tags=["商品管理"]
)
async def create_product(product: ProductCreate):
    """
    创建商品接口
    
    - **name**: 商品名称，1-100 字符
    - **price**: 商品价格，单位元
    - **category**: 商品分类，只能从枚举值中选择
    - **stock**: 初始库存，默认为 0
    """
    # 实际业务逻辑...
    return ProductResponse(
        id=1,
        name=product.name,
        price=product.price,
        category=product.category.value,
        stock=product.stock,
        created_at="2024-01-01T00:00:00Z"
    )

@app.get(
    "/api/v1/products",
    response_model=List[ProductResponse],
    summary="获取商品列表",
    tags=["商品管理"]
)
async def list_products(
    category: Optional[ProductCategory] = Query(None, description="按分类筛选"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """
    分页获取商品列表，支持按分类和价格筛选
    
    返回结果按创建时间倒序排列
    """
    # 实际查询逻辑...
    return []
```

**访问生成的文档：**
- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`
- OpenAPI JSON：`http://localhost:8000/openapi.json`

### API 版本管理策略

API 版本管理是长期维护项目必须考虑的问题。一旦 API 发布，就不能随意修改接口契约，否则会破坏已有的客户端。

**常用的版本管理策略：**

| 策略 | 示例 | 优点 | 缺点 |
|------|------|------|------|
| URL 路径 | `/api/v1/users` | 最直观，缓存友好 | URL 冗长 |
| 请求头 | `Accept: application/vnd.api.v1+json` | URL 干净 | 不够直观，调试麻烦 |
| 查询参数 | `/api/users?version=1` | 灵活 | 不符合 REST 风格 |
| 域名 | `api-v1.example.com` | 完全隔离 | 运维成本高 |

**URL 路径版本的 Python 实现：**

```python
from fastapi import FastAPI, APIRouter

app = FastAPI()

# v1 路由
v1_router = APIRouter(prefix="/api/v1")

@v1_router.get("/users")
async def list_users_v1():
    """v1 版本：返回基础用户信息"""
    return {"version": "v1", "users": [{"id": 1, "name": "Alice"}]}

# v2 路由 —— 增加了 email 字段，调整了返回结构
v2_router = APIRouter(prefix="/api/v2")

@v2_router.get("/users")
async def list_users_v2():
    """v2 版本：返回完整用户信息"""
    return {
        "version": "v2",
        "data": [{"id": 1, "name": "Alice", "email": "alice@example.com"}],
        "total": 1
    }

app.include_router(v1_router)
app.include_router(v2_router)
```

**版本演进的最佳实践：**

1. **兼容性变更无需版本升级**：新增可选参数、新增响应字段都是向后兼容的
2. **破坏性变更才需要版本升级**：删除字段、修改字段类型、改变 URL 路径
3. **维护窗口期**：同时支持多个版本，给客户端迁移时间（通常 6-12 个月）
4. **Sunset 机制**：在响应头中标注 API 废弃信息

```python
from fastapi import Response

@app.get("/api/v1/legacy-endpoint")
async def legacy_endpoint(response: Response):
    """已废弃的接口，返回 Sunset 信息"""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 31 Dec 2024 23:59:59 GMT"
    response.headers["Link"] = '</api/v2/new-endpoint>; rel="successor-version"'
    return {"message": "此接口将于 2024 年底废弃，请迁移到 v2"}
```

### 常见面试题

#### 面试题 1：如何设计一个"向后兼容"的 API 变更？

**参考答案：**

向后兼容（Backward Compatible）的 API 变更是指：新版本的 API 仍然能被旧客户端正常消费，无需修改客户端代码。

**兼容的变更（无需版本升级）：**
- ✅ 新增可选的请求参数
- ✅ 新增响应字段（客户端应忽略不认识字段）
- ✅ 放宽参数校验（如最小长度从 5 改为 3）
- ✅ 新增接口（不影响现有接口）

**不兼容的变更（需要版本升级）：**
- ❌ 删除或重命名字段
- ❌ 改变字段数据类型
- ❌ 将可选参数改为必填
- ❌ 改变接口 URL 路径
- ❌ 改变错误响应结构

**向后兼容的设计技巧：**

```python
class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    # 新增字段时设置默认值，确保旧客户端不报错
    avatar_url: Optional[str] = Field(
        default=None,
        description="用户头像 URL（v1.2 新增）"
    )
    # 即将删除的字段：保留但标注废弃
    old_field: Optional[str] = Field(
        default=None,
        deprecated=True,
        description="此字段将在 v2 中移除，请使用 new_field"
    )
    
    class Config:
        # 允许客户端接收额外的未知字段（超集兼容）
        extra = "ignore"
```

#### 面试题 2：当需要同时维护多个 API 版本时，如何组织代码结构？

**参考答案：**

推荐按版本组织路由和模型，但共享业务逻辑层：

```
project/
├── api/
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── router.py       # v1 路由聚合
│   │   ├── schemas.py      # v1 Pydantic 模型
│   │   └── endpoints/      # v1 端点实现
│   └── v2/
│       ├── __init__.py
│       ├── router.py
│       ├── schemas.py
│       └── endpoints/
├── services/               # 业务逻辑层：版本无关，所有 API 版本共享
│   └── user_service.py
└── main.py                 # 注册所有版本路由
```

**核心原则：**
1. **业务逻辑共享**：Service 层不感知 API 版本，只处理领域对象
2. **数据转换隔离**：每个版本的 Schema 负责与 Service 层的转换
3. **避免复制粘贴**：v2 的端点如果逻辑与 v1 相同，应直接复用 Service，而不是复制代码

---

## 单元测试与集成测试

### 测试金字塔

测试策略遵循"测试金字塔"原则：底层单元测试数量最多、执行最快；上层集成测试和 E2E 测试数量较少但覆盖更广。

```
        /\
       /  \     E2E 测试（少量，覆盖关键用户旅程）
      /____\
     /      \   集成测试（中等数量，验证模块协作）
    /________\
   /          \ 单元测试（大量，验证单个函数/类）
  /____________\
```

**各层测试的特点：**

| 类型 | 范围 | 速度 | 稳定性 | 维护成本 | 定位问题 |
|------|------|------|--------|----------|----------|
| 单元测试 | 单个函数/类 | 毫秒级 | 高 | 低 | 精确到行 |
| 集成测试 | 多个模块协作 | 秒级 | 中 | 中 | 精确到模块 |
| E2E 测试 | 完整用户流程 | 分钟级 | 低 | 高 | 粗略 |

### pytest —— Python 测试的事实标准

pytest 是 Python 生态中最流行的测试框架，它通过简单的断言和强大的 fixture 系统，让编写测试变得愉悦。

```python
# tests/test_calculator.py
import pytest
from src.calculator import Calculator

# 使用 fixture 创建测试所需的资源
@pytest.fixture
def calc():
    """每个测试用例都会获得一个新的 Calculator 实例"""
    return Calculator()

# 简单的单元测试
class TestCalculator:
    def test_add(self, calc):
        """测试加法"""
        assert calc.add(2, 3) == 5
        assert calc.add(-1, 1) == 0
        assert calc.add(0, 0) == 0
    
    def test_divide(self, calc):
        """测试除法"""
        assert calc.divide(10, 2) == 5
        
        # 测试异常情况
        with pytest.raises(ZeroDivisionError):
            calc.divide(10, 0)
    
    # 参数化测试：用多组数据测试同一逻辑
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            (2, 3, 5),
            (-1, -1, -2),
            (0, 100, 100),
            (1.5, 2.5, 4.0),
        ]
    )
    def test_add_parametrized(self, calc, a, b, expected):
        """参数化加法测试"""
        assert calc.add(a, b) == expected
```

**Fixture 的高级用法：**

```python
# conftest.py —— 共享的 fixture 定义
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import app
from database import Base, get_db

# scope="session"：整个测试会话只执行一次
@pytest.fixture(scope="session")
def engine():
    """创建内存数据库引擎"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

# scope="function"：每个测试函数执行一次（默认）
@pytest.fixture
def db_session(engine):
    """为每个测试提供独立的数据库会话"""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    
    yield session
    
    # 清理：回滚事务，确保测试互不干扰
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    """创建 FastAPI 测试客户端，注入测试数据库会话"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # 替换依赖注入
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    # 清理依赖覆盖
    app.dependency_overrides.clear()
```

**接口测试示例：**

```python
# tests/api/test_user_api.py
class TestUserAPI:
    def test_create_user(self, client):
        """测试创建用户接口"""
        response = client.post(
            "/api/v1/users",
            json={"name": "Alice", "email": "alice@example.com", "password": "secret123"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Alice"
        assert "id" in data
        assert "password" not in data  # 确保密码不返回
    
    def test_get_user_not_found(self, client):
        """测试获取不存在的用户"""
        response = client.get("/api/v1/users/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "用户不存在"
    
    def test_create_user_invalid_email(self, client):
        """测试参数校验"""
        response = client.post(
            "/api/v1/users",
            json={"name": "Bob", "email": "invalid-email", "password": "short"}
        )
        assert response.status_code == 422
```

### 测试覆盖率

覆盖率衡量测试代码对被测代码的覆盖程度，是最基础的测试质量指标。

```bash
# 安装 coverage 工具
pip install pytest-cov

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=term-missing

# 生成 HTML 报告（可视化查看未覆盖的代码）
pytest --cov=src --cov-report=html

# 在 CI 中设置覆盖率门槛
pytest --cov=src --cov-fail-under=80  # 覆盖率低于 80% 则构建失败
```

**`pyproject.toml` 配置：**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
# 忽略的行
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
# 覆盖率低于此值时失败
fail_under = 80
```

**覆盖率指标的局限性：**
- 高覆盖率不等于高质量测试（可能测试了代码路径但没有验证正确性）
- 不要为了覆盖率而写无意义的测试
- 核心业务流程的覆盖率应该高于辅助工具代码
- 边界条件和异常路径同样重要

### Mock 与依赖隔离

单元测试的核心原则是**隔离被测单元**，使用 Mock 对象替代真实的依赖。

```python
from unittest.mock import Mock, patch, AsyncMock
import pytest
from services.order_service import OrderService

class TestOrderService:
    @pytest.fixture
    def service(self):
        """创建 OrderService，注入 Mock 对象"""
        mock_repo = Mock()
        mock_payment = AsyncMock()
        return OrderService(mock_repo, mock_payment)
    
    def test_create_order_calls_repo(self, service):
        """测试创建订单时会调用仓储"""
        # 设置 Mock 返回值
        service._repo.create.return_value = {"id": 1, "total": 100}
        
        # 执行被测方法
        result = service.create_order(user_id=1, items=[])
        
        # 验证依赖被正确调用
        service._repo.create.assert_called_once()
        assert result["id"] == 1
    
    @patch("services.order_service.send_email")
    def test_order_notification(self, mock_send_email, service):
        """使用 patch 替换模块级别的函数"""
        service._repo.create.return_value = {"id": 1}
        
        service.create_order(user_id=1, items=[])
        
        # 验证邮件通知被发送
        mock_send_email.assert_called_once_with(
            to="user@example.com",
            subject="订单创建成功",
            body=pytest.ANY  # 不验证具体内容
        )
    
    @pytest.mark.asyncio
    async def test_async_payment(self, service):
        """测试异步支付调用"""
        service._payment.process.return_value = {"status": "success"}
        
        result = await service.process_payment(order_id=1)
        
        service._payment.process.assert_awaited_once_with(order_id=1)
        assert result["status"] == "success"
```

**Mock 最佳实践：**
- 尽量 Mock "边界"依赖（数据库、HTTP 调用、消息队列），不要 Mock 被测单元内部的逻辑
- 使用 `spec` 参数确保 Mock 对象与真实对象接口一致：`Mock(spec=RealClass)`
- 优先验证"行为"（assert_called_with）而非"状态"，确保测试的是交互而非实现细节

### 常见面试题

#### 面试题 1：单元测试中，"应该 Mock 什么，不应该 Mock 什么"？

**参考答案：**

**应该 Mock 的：**
- 外部依赖：数据库、Redis、第三方 HTTP API、消息队列、文件系统
- 耗时操作：复杂计算、网络请求、发送邮件/SMS
- 不可控依赖：当前时间、随机数生成器、UUID 生成

**不应该 Mock 的：**
- 被测单元本身的内部逻辑（否则测了个寂寞）
- 简单的值对象和数据结构（直接构造即可）
- 稳定的、经过充分测试的基础库（如 Python 内置函数）

**面试加分回答：** 在测试金字塔中，单元测试 Mock 外部依赖，集成测试使用真实的（或轻量级的）依赖（如 Testcontainers 启动真实数据库），E2E 测试使用完整的生产环境。

#### 面试题 2：如何保证测试之间的独立性？如果测试顺序影响结果，说明什么问题？

**参考答案：**

测试之间必须是**独立的、可重复执行的**，任何测试都不应依赖其他测试的执行顺序或副作用。

如果测试顺序影响结果，说明存在以下问题：

1. **共享可变状态**：测试之间共享了全局变量、单例对象或数据库记录
2. **资源未清理**：测试 A 创建的数据没有被清理，影响了测试 B
3. **外部依赖污染**：测试修改了文件系统、环境变量等全局状态

**解决方案：**

```python
# 方案 1：使用 fixture 的 setup/teardown
@pytest.fixture
def temp_file():
    """每个测试使用独立的临时文件"""
    path = "/tmp/test_file.txt"
    yield path
    # teardown：测试结束后清理
    if os.path.exists(path):
        os.remove(path)

# 方案 2：数据库事务回滚（最快的方案）
@pytest.fixture
def db_session():
    transaction = connection.begin_nested()
    yield session
    transaction.rollback()  # 回滚所有更改

# 方案 3：每个测试使用独立的数据库
@pytest.fixture
def fresh_db():
    """为测试创建全新的数据库"""
    db_name = f"test_db_{uuid.uuid4().hex}"
    create_database(db_name)
    yield db_name
    drop_database(db_name)
```

---

## 性能调优与压测

### 性能优化的基本原则

Donald Knuth 的名言"过早优化是万恶之源"经常被误用。正确的理解是：
- **不要盲目优化**：在没有测量的情况下优化，往往优化的是不重要的代码
- **必须测量**：用数据驱动优化决策，而不是凭感觉
- **关注热点**：80% 的执行时间消耗在 20% 的代码上，找到这 20%

性能优化的正确流程：

```
1. 建立性能基线（Benchmark）
        ↓
2. 识别瓶颈（Profile）
        ↓
3. 优化瓶颈
        ↓
4. 验证优化效果
        ↓
5. 重复 1-4，直到满足目标
```

### Python 性能分析工具

```python
# 1. cProfile —— 标准库内置的确定性性能分析器
import cProfile
import pstats

# 分析函数执行
profiler = cProfile.Profile()
profiler.enable()

# 被分析的代码
result = process_large_dataset(data)

profiler.disable()

# 输出统计结果
stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")  # 按累计时间排序
stats.print_stats(20)  # 显示前 20 个耗时最多的函数

# 2. line_profiler —— 行级分析（需要 pip install line-profiler）
# 在要分析的函数上加装饰器
from line_profiler import profile

@profile
def heavy_computation():
    result = []
    for i in range(100000):
        result.append(i ** 2)  # 每行耗时都会被记录
    return result

# 3. memory_profiler —— 内存分析（需要 pip install memory-profiler）
from memory_profiler import profile

@profile
def memory_intensive():
    large_list = [0] * 10000000  # 这会消耗大量内存
    return sum(large_list)
```

**解读 Profile 结果的关键指标：**

| 指标 | 含义 | 优化方向 |
|------|------|----------|
| `ncalls` | 调用次数 | 如果次数异常高，可能存在循环中的重复调用 |
| `tottime` | 函数本身执行时间（不含子调用） | 函数本身需要优化 |
| `cumtime` | 累计时间（含子调用） | 可能子调用是瓶颈 |
| `percall` | 每次调用平均时间 | 定位具体慢的操作 |

### 常见性能优化技巧

**1. 算法优化（Big O 优化）**

```python
# ❌ O(n²) —— 查找重复元素
def find_duplicates_slow(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                duplicates.append(items[i])
    return duplicates

# ✅ O(n) —— 使用集合
def find_duplicates_fast(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)
```

**2. 使用生成器节省内存**

```python
# ❌ 一次性加载所有数据到内存

def process_large_file_slow(filepath):
    with open(filepath) as f:
        lines = f.readlines()  # 100 万行 = 大量内存
    return [line.strip() for line in lines if "ERROR" in line]

# ✅ 逐行处理，内存占用恒定
def process_large_file_fast(filepath):
    with open(filepath) as f:
        for line in f:  # 每次只读取一行
            if "ERROR" in line:
                yield line.strip()

# 使用
for error_line in process_large_file_fast("huge.log"):
    process(error_line)
```

**3. 避免重复计算 —— 缓存**

```python
from functools import lru_cache

# 自动缓存最近 128 次调用结果
@lru_cache(maxsize=128)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# 第一次调用 fibonacci(30) 会计算
# 第二次调用 fibonacci(30) 直接从缓存返回

# 对于带参数的缓存，参数必须可哈希
@lru_cache(maxsize=1024)
def get_user_from_db(user_id: int):
    """缓存数据库查询结果"""
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
```

**4. 批量操作减少 I/O**

```python
# ❌ 逐条插入（N 次数据库往返）
for user in users:
    db.execute("INSERT INTO users (name, email) VALUES (?, ?)", (user.name, user.email))

# ✅ 批量插入（1 次数据库往返）
# SQLAlchemy
session.bulk_insert_mappings(User, [u.__dict__ for u in users])

# PostgreSQL COPY 协议（最快）
from io import StringIO
buffer = StringIO()
for user in users:
    buffer.write(f"{user.name}\t{user.email}\n")
buffer.seek(0)
cursor.copy_from(buffer, "users", columns=("name", "email"))
```

### 压力测试工具

**Locust —— Python 生态的负载测试工具**

Locust 使用 Python 编写测试脚本，可以模拟成千上万的并发用户。

```python
# locustfile.py
from locust import HttpUser, task, between

class WebsiteUser(HttpUser):
    """模拟真实用户行为"""
    
    # 用户操作之间的等待时间（1-5 秒随机）
    wait_time = between(1, 5)
    
    def on_start(self):
        """每个用户启动时执行：模拟登录"""
        self.client.post("/api/v1/auth/login", json={
            "email": "user@example.com",
            "password": "password123"
        })
    
    @task(10)  # 权重 10，执行频率最高
    def browse_products(self):
        """浏览商品列表"""
        self.client.get("/api/v1/products?page=1&page_size=20")
    
    @task(5)
    def view_product_detail(self):
        """查看商品详情"""
        self.client.get("/api/v1/products/1")
    
    @task(2)
    def add_to_cart(self):
        """添加购物车"""
        self.client.post("/api/v1/cart/items", json={
            "product_id": 1,
            "quantity": 1
        })
    
    @task(1)
    def create_order(self):
        """创建订单（最少执行）"""
        self.client.post("/api/v1/orders", json={
            "items": [{"product_id": 1, "quantity": 1}]
        })
```

```bash
# 启动 Locust
locust -f locustfile.py --host=http://localhost:8000

# 命令行模式（无 UI，适合 CI）
locust -f locustfile.py --host=http://localhost:8000 \
    --users 1000 --spawn-rate 100 --run-time 5m \
    --headless --csv=load_test
```

**Apache Bench (ab) —— 快速测试单个接口**

```bash
# 发送 10000 个请求，100 个并发
ab -n 10000 -c 100 http://localhost:8000/api/v1/products

# 带请求头的测试
ab -n 1000 -c 10 -H "Authorization: Bearer token" \
   http://localhost:8000/api/v1/users/me

# POST 请求测试
ab -n 1000 -c 10 -p body.json -T application/json \
   http://localhost:8000/api/v1/users
```

**Locust vs ab 的选择：**

| 工具 | 适用场景 | 优势 | 劣势 |
|------|----------|------|------|
| ab | 快速测试单个接口 | 零配置，开箱即用 | 只能测试简单场景 |
| Locust | 复杂用户行为模拟 | Python 脚本，灵活 | 需要编写代码 |
| k6 | 现代云原生测试 | JS 脚本，内置云 | 学习曲线 |

### 常见面试题

#### 面试题 1：如果发现一个接口响应慢，你的排查思路是什么？

**参考答案：**

系统化的排查思路：

1. **确认问题范围**
   - 是所有请求都慢，还是特定接口慢？
   - 是特定时间段慢，还是持续慢？
   - 是单机慢，还是集群都慢？

2. **分析各层耗时**
   ```
   总响应时间 = DNS 解析 + TCP 握手 + SSL 握手 + 服务器处理 + 网络传输
   ```
   - 用 `curl -w` 查看各阶段时间：`curl -w "@curl-format.txt" -o /dev/null -s URL`
   - 用 Chrome DevTools 的 Network 面板

3. **定位服务器端瓶颈**
   - 应用层：`cProfile` / `line_profiler` 定位 Python 代码热点
   - 数据库层：慢查询日志、EXPLAIN 分析 SQL 执行计划
   - 缓存层：Redis `MONITOR`、`SLOWLOG`
   - 外部调用：追踪 HTTP/RPC 调用耗时

4. **系统资源检查**
   - `top` / `htop`：CPU 使用率
   - `free -h`：内存是否耗尽
   - `iostat`：磁盘 I/O 是否饱和
   - `netstat`/`ss`：连接数是否达到上限

5. **常见根因**
   | 现象 | 可能原因 |
   |------|----------|
   | CPU 高，响应慢 | 复杂计算、序列化开销、GC 频繁 |
   | CPU 低，响应慢 | I/O 阻塞（数据库、网络）、锁竞争 |
   | 内存持续增长 | 内存泄漏、缓存未设过期 |
   | 偶发超时 | 网络抖动、依赖服务不稳定 |

#### 面试题 2：如何设计一个可以支撑 10 万 QPS 的接口？

**参考答案：**

10 万 QPS 是一个极高的目标，需要从多个层面设计：

**1. 接入层 —— 负载均衡**
```
用户请求 → DNS 轮询 → CDN（静态资源）→ LVS/HAProxy → Nginx 集群
```
- 使用 Anycast DNS 就近路由
- 四层负载均衡（LVS）处理海量连接
- Nginx 做七层路由和限流

**2. 应用层 —— 水平扩展**
```python
# 无状态设计：不在本地内存存储用户数据
# 所有状态存储在 Redis/数据库中

# 示例：用户 Session 不存内存，存 Redis
from fastapi import Depends
from redis import Redis

redis = Redis(host="redis-cluster")

def get_current_user(token: str = Depends(oauth2_scheme)):
    # 从 Redis 获取 session，不依赖本地内存
    user_data = redis.get(f"session:{token}")
    if not user_data:
        raise HTTPException(401, "未登录")
    return json.loads(user_data)
```

**3. 缓存层 —— 减少数据库压力**
```
用户请求 → 本地缓存（Caffeine/进程内）→ 分布式缓存（Redis Cluster）→ 数据库
```
- 缓存命中率目标 > 95%
- 热点数据多级缓存：浏览器缓存 → CDN → Nginx 缓存 → 应用缓存 → Redis
- 缓存更新策略：Cache-Aside + 消息队列异步刷新

**4. 数据库层 —— 读写分离 + 分片**
```python
# SQLAlchemy 读写分离配置
class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None, **kw):
        if self._flushing:  # 写操作
            return engines["master"]
        return engines["slave"]  # 读操作路由到从库
```

**5. 异步化 —— 非阻塞 I/O**
```python
# 使用 async/await 避免线程阻塞
@app.get("/hot-products")
async def get_hot_products():
    # 并行发起多个异步请求
    products, stats = await asyncio.gather(
        redis.get("hot_products"),
        fetch_realtime_stats()  # 异步 HTTP 调用
    )
    return {"products": products, "stats": stats}
```

**6. 限流与降级**
```python
from fastapi_limiter import FastAPILimiter

@app.get("/api/v1/products")
@limiter.limit("100/second")  # 每秒最多 100 请求
async def list_products():
    pass

# 熔断器：下游服务故障时快速失败
@circuit_breaker(threshold=5, timeout=30)
async def call_payment_service():
    # 如果连续 5 次失败，30 秒内直接返回错误
    pass
```

---

## 常见面试项目问题与回答思路

### 如何介绍你的项目？—— STAR 法则

面试官问"介绍一下你做过的项目"时，不是想听技术栈罗列，而是想了解你的**工程能力、问题解决能力和影响力**。

推荐使用 **STAR 法则**组织回答：

| 部分 | 内容 | 示例 |
|------|------|------|
| **S**ituation（背景） | 项目是什么？什么业务场景？团队规模？ | "我在上一家公司负责电商平台的订单系统，团队 5 人，日活 50 万" |
| **T**ask（任务） | 你的具体职责？面对什么挑战？ | "我负责订单状态机和支付对接，核心挑战是高并发下的数据一致性" |
| **A**ction（行动） | 你做了什么？用了什么技术？ | "我引入了状态机模式管理订单状态，用 Redis 分布式锁防止超卖" |
| **R**esult（结果） | 取得了什么成果？最好有数据 | "系统稳定性从 99.5% 提升到 99.95%，订单处理峰值从 1000 QPS 提升到 5000 QPS" |

### 高频面试题精选

#### 面试题 1：如何设计一个高并发系统？

**回答思路：**

高并发不是单一技术能解决的，而是一套**分层优化的体系**：

```
┌─────────────────────────────────────┐
│  客户端：减少请求（缓存、合并请求）      │
├─────────────────────────────────────┤
│  CDN：就近分发静态资源                 │
├─────────────────────────────────────┤
│  接入层：负载均衡、限流、降级            │
├─────────────────────────────────────┤
│  应用层：无状态设计、水平扩展、异步化     │
├─────────────────────────────────────┤
│  缓存层：多级缓存、热点数据预加载         │
├─────────────────────────────────────┤
│  数据层：读写分离、分库分表、索引优化     │
├─────────────────────────────────────┤
│  基础设施：容器化、自动扩缩容             │
└─────────────────────────────────────┘
```

**关键要点：**
1. **无状态**：应用服务器不保存会话，所有状态外置（Redis/数据库）
2. **读写分离**：读多写少的场景，读走从库，写走主库
3. **缓存为王**：80% 的请求应该在缓存层拦截
4. **异步化**：非核心流程异步处理（发送通知、更新统计）
5. **降级预案**：高峰期关闭非核心功能，保障核心链路

#### 面试题 2：数据库慢查询如何排查和优化？

**回答思路：**

```
1. 发现问题
   - 慢查询日志：MySQL `slow_query_log`，PostgreSQL `log_min_duration_statement`
   - APM 工具：NewRelic、Datadog、SkyWalking
   - 用户反馈：特定页面加载慢

2. 分析执行计划
   EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = 123;
   
   关注：
   - type：ALL（全表扫描）→ 需要优化
   - rows：扫描行数，评估索引效果
   - Extra：Using filesort、Using temporary → 性能警告

3. 优化手段
   a. 索引优化
      - WHERE、JOIN、ORDER BY 字段加索引
      - 联合索引注意最左前缀原则
      - 避免索引失效（函数操作、类型转换、前导模糊查询）
   
   b. SQL 优化
      - 避免 SELECT *，只查需要的字段
      - 大表分页用覆盖索引 + JOIN 替代 OFFSET
      - 深分页优化：WHERE id > ? LIMIT 代替 OFFSET
   
   c. 架构优化
      - 读写分离：报表查询走从库
      - 分库分表：单表数据量控制在 1000 万以内
      - 引入搜索引擎：复杂查询用 Elasticsearch
      - 缓存：热点查询结果缓存
```

**Python 中的实践示例：**

```python
# ❌ 慢查询：深分页 OFFSET 100000 会导致数据库扫描 10 万行
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20 OFFSET 100000;

# ✅ 优化：基于索引列的范围查询
SELECT * FROM orders 
WHERE created_at < '2024-01-01'  # 利用 created_at 索引
ORDER BY created_at DESC 
LIMIT 20;

# ✅ 更好的方案：游标分页（适合无限滚动场景）
SELECT * FROM orders 
WHERE (created_at, id) < (last_created_at, last_id)  # 上一页最后一条记录
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

#### 面试题 3：如何保障系统稳定性？

**回答思路：**

稳定性建设是一个系统工程，从预防、监控到应急形成闭环：

**1. 预防 —— 减少故障发生**
- 代码质量：Code Review、静态分析、自动化测试
- 发布控制：灰度发布、蓝绿部署、金丝雀发布
- 容量规划：压测确定系统上限，预留 30% 余量
- 变更管理：所有线上变更需要审批和回滚方案

**2. 监控 —— 快速发现问题**
```python
# 关键指标监控（RED 方法）
# Rate（请求率）- 系统每秒接收多少请求
# Errors（错误率）- 多少请求失败
# Duration（延迟）- 请求处理耗时

# 使用 Prometheus + Grafana 监控
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter('http_requests_total', '总请求数', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', '请求耗时', ['method', 'endpoint'])

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response
```

**3. 应急 —— 故障发生时快速恢复**
- 熔断降级：服务故障时快速失败，不拖垮整个系统
- 限流：防止流量突增压垮服务
- 自动扩缩容：K8s HPA 根据 CPU/内存自动调整副本数
- 一键回滚：发布出问题能在 5 分钟内回滚

**4. 复盘 —— 从故障中学习**
- 故障定级：P0（核心功能不可用）、P1（核心功能降级）、P2（非核心功能）
- 根因分析：5 Whys 方法，追问到根本原因
- 改进措施：每个故障必须有可落地的改进项
- 演练：定期做混沌工程演练（Chaos Engineering）

#### 面试题 4：从零开始设计一个电商订单系统，你会怎么设计？

**回答思路：**

这是一个经典的系统设计题，考察的是**需求分析 → 领域建模 → 架构设计 → 关键问题处理**的完整思维链。

**1. 需求澄清（先问清楚边界）**
- 业务规模：日订单量？峰值 QPS？
- 商品类型：实物商品？虚拟商品？预售？
- 支付渠道：微信支付、支付宝、银联？
- 物流对接：是否需要对接快递公司？

**2. 领域建模**

```python
# 核心聚合：Order（订单聚合根）
class Order:
    def __init__(self, order_id, user_id, items, address):
        self._id = order_id
        self._user_id = user_id
        self._items = items  # OrderItem 列表
        self._address = address
        self._status = OrderStatus.CREATED
        self._payment = None
        self._created_at = datetime.now()
    
    def submit(self):
        """提交订单：状态机转换"""
        if self._status != OrderStatus.CREATED:
            raise InvalidOrderState("订单已提交")
        self._status = OrderStatus.SUBMITTED
        self.record_event(OrderSubmitted(self._id))
    
    def pay(self, payment_info):
        """支付"""
        if self._status != OrderStatus.SUBMITTED:
            raise InvalidOrderState("订单未提交或已支付")
        self._payment = Payment(payment_info)
        self._status = OrderStatus.PAID
        self.record_event(OrderPaid(self._id))
    
    def ship(self, tracking_number):
        """发货"""
        if self._status != OrderStatus.PAID:
            raise InvalidOrderState("订单未支付")
        self._status = OrderStatus.SHIPPED
        self._tracking_number = tracking_number
    
    def complete(self):
        """完成"""
        if self._status != OrderStatus.SHIPPED:
            raise InvalidOrderState("订单未发货")
        self._status = OrderStatus.COMPLETED
```

**3. 状态机设计**

```
CREATED → SUBMITTED → PAID → SHIPPED → COMPLETED
   ↓          ↓         ↓
 CANCELLED  CANCELLED  REFUNDED
```

**4. 关键问题处理**

| 问题 | 解决方案 |
|------|----------|
| 超卖 | Redis 分布式锁 + 数据库唯一约束 + 异步库存回滚 |
| 重复支付 | 支付接口幂等设计（幂等键：order_id + payment_no） |
| 分布式事务 | Saga 模式：订单创建 → 扣库存 → 创建支付单，失败则补偿 |
| 高并发下单 | 消息队列削峰，异步创建订单，前端展示"排队中" |
| 数据一致性 | 最终一致性：消息队列保证事件投递，对账系统兜底 |

**5. 架构设计**

```
用户 → API Gateway → 订单服务 → 消息队列（Kafka/RabbitMQ）
                           ↓
                     ┌─────┴─────┐
                     ↓           ↓
                  库存服务    支付服务
                     ↓           ↓
                  Redis      第三方支付
                     ↓
                  MySQL（订单库 + 库存库）
```

---

## 本章小结

项目工程化能力是从"写代码"到"做工程"的关键跃迁。本章覆盖了项目落地的六个核心维度：

1. **项目结构**：分层架构是最实用的起点，Clean Architecture 和 DDD 适用于复杂业务，但切忌过度设计
2. **代码规范**：Black + Ruff + pre-commit 构成现代化的 Python 代码质量保障体系
3. **接口文档**：FastAPI 的自动生成 + 版本管理策略，确保 API 的可维护性和向后兼容
4. **测试体系**：pytest 提供强大的测试能力，Mock 实现依赖隔离，覆盖率确保测试有效性
5. **性能调优**：先测量再优化，cProfile 定位热点，Locust 验证性能目标
6. **面试应答**：用 STAR 法则组织项目介绍，系统化回答高并发、慢查询、稳定性等高频问题

记住，架构没有银弹，最适合当前团队规模和业务复杂度的架构就是最好的架构。随着业务演进，架构也应该持续演进。

