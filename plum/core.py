# -*- coding: utf-8 -*-
"""
Created on Sun Aug 11 13:37:22 2024

@author: Administrator
"""

import weakref
import contextlib
import numpy as np


class Config:
  enable_backprop = True
  train = True


@contextlib.contextmanager
def using_config(name, value):
  old_value = getattr(Config, name)
  setattr(Config, name, value)
  try:
    yield
  finally:
    setattr(Config, name, old_value)
    
  
def no_grad():
  return using_config('enable_backprop', False)

def test_mode():
  return using_config('train', False)
    

try:
  import cupy
  array_types = (np.ndarray, cupy.ndarray)
except ImportError:
  array_types = (np.ndarray)


class Variable:
  __array_priority__ = 200

  def __init__(self, data, name=None):
    if data is not None:
      if not isinstance(data, array_types):
        raise TypeError('{} is not supported'.format(type(data)))
    self.data = data
    self.name = name
    self.grad = None
    self.creator = None
    self.generation = 0

  def backward(self, retain_grad=False):
    if self.grad is None:
      self.grad = np.ones_like(self.data)

    funcs = []
    seen_set = set()
    def add_func(f):
      if f not in seen_set:
        funcs.append(f)
        seen_set.add(f)
        funcs.sort(key = lambda x: x.generation)

    add_func(self.creator)
    while funcs:
      f = funcs.pop()
      gys = [output().grad for output in f.outputs]
      gxs = f.backward(*gys)
      if not isinstance(gxs, tuple):
        gxs = (gxs, )

      for x, gx in zip(f.inputs, gxs):
        if x.grad is None:
          x.grad = gx
        else:
          x.grad = x.grad + gx

        if x.creator is not None:
          add_func(x.creator)
      if not retain_grad:
        for output in f.outputs:
          output().grad = None


  def set_creator(self, creator):
    self.creator = creator
    self.generation = creator.generation + 1

  def unchain(self):
    self.creator = None

  def cleargrad(self):
    self.grad = None

  @property
  def shape(self):
    return self.data.shape

  @property
  def ndim(self):
    return self.data.ndim

  @property
  def size(self):
    return self.data.size
    
  @property
  def dtype(self):
    return self.data.dtype

  def __len__(self):
    return len(self.data)

  def __repr__(self):
    if self.data is None:
      return 'Variable(None)'
    p = str(self.data).replace('\n', '\n' + ' ' * 9)
    return 'Variable(' + p + ')'

  def reshape(self, *shape):
    if len(shape) == 1 and isinstance(shape[0], (tuple, list)):
      shape = shape[0]
    return reshape(self, shape)


def as_variable(obj):
  if isinstance(obj, Variable):
    return obj
  return Variable(obj)

def as_array(x):
  if np.isscalar(x):
    return np.array(x)
  return x

class Function:
  def __call__(self, *inputs):
    print('inputs:', inputs)
    inputs = [as_variable(x) for x in inputs]
    xs = [x.data for x in inputs]
    ys = self.forward(*xs)
    if not isinstance(ys, tuple):
      ys = (ys, )
    outputs = [Variable(as_array(y)) for y in ys]

    if Config.enable_backprop:
      self.generation = max([x.generation for x in inputs])
      for output in outputs:
        output.set_creator(self)
      self.inputs = inputs
      self.outputs = [weakref.ref(output) for output in outputs]
    return outputs if len(outputs) > 1 else outputs[0]
  
  def forward(self, xs):
    raise NotImplementedError()
    
  def backward(self, gys):
    raise NotImplementedError()


class Add(Function):
  def forward(self, x0, x1):
    self.x0_shape = x0.shape
    self.x1_shape = x1.shape
    y = x0 + x1
    return y

  def backward(self, gy):
    return gy, gy

def add(x0, x1):
  x1 = as_array(x1)
  return Add()(x0, x1)

class Mul(Function):
  def forward(self, x0, x1):
    y = x0 * x1
    return y

  def backward(self, gy):
    x0, x1 = self.inputs
    x0 = x0.data
    x1 = x1.data
    gx0 = gy * x1
    gx1 = gy * x0
    return gx0, gx1

def mul(x0, x1):
  x1 = as_array(x1)
  return Mul()(x0, x1)

class Neg(Function):
  def forward(self, x):
    return -x

  def backward(self, gy):
    return -gy

def neg(x):
  return Neg()(x)

class Sub(Function):
  def forward(self, x0, x1):
    return x0 - x1

  def backward(self, gy):
    return gy, -gy

def sub(x0, x1):
  x1 = as_array(x1)
  return Sub()(x0, x1)

def rsub(x0, x1):
  x1 = as_array(x1)
  return Sub()(x1, x0)

class Div(Function):
  def forward(self, x0, x1):
    return x0 / x1

  def backward(self, gy):
    x0, x1 = self.inputs
    x0 = x0.data
    x1 = x1.data
    gx0 = gy / x1
    gx1 = gy * (-x0) / (x1**2)
    return gx0, gx1

def div(x0, x1):
  x1 = as_array(x1)
  return Div()(x0, x1)

def rdiv(x0, x1):
  x1 = as_array(x1)
  return Div()(x1, x0)

class Pow(Function):
  def __init__(self, c):
    super().__init__()
    self.c = c

  def forward(self, x):
    return x ** self.c

  def backward(self, gy):
    x = self.inputs[0].data
    c = self.c
    return c * x ** (c-1) * gy

def pow(x, c):
  return Pow(c)(x)

class Sin(Function):
  def forward(self, x):
    y = np.sin(x)
    return y

  def backward(self, gy):
    x = self.inputs[0].data
    gx = gy * np.cos(x)
    return gx

def sin(x):
  return Sin()(x)

class Cos(Function):
  def forward(self, x):
    y = np.cos(x)
    return y

  def backward(self, gy):
    x, = self.inputs
    gx = gy * -sin(x)
    return gx

def cos(x):
  return Cos()(x)


class Reshape(Function):
  def __init__(self, shape):
    self.shape = shape

  def forward(self, x):
    self.x_shape = x.shape
    y = x.reshape(self.shape)
    return y

  def backward(self, gy):
    return reshape(gy, self.x_shape)

def reshape(x, shape):
  if x.shape == shape:
    return as_variable(x)
  return Reshape(shape)(x)


def setup_variable():
  Variable.__add__ = add
  Variable.__radd__ = add
  Variable.__mul__ = mul
  Variable.__rmul__ = mul
  Variable.__sub__ = sub
  Variable.__rsub__ = rsub
  Variable.__truediv__ = div
  Variable.__rtruediv__ = rdiv
  Variable.__pow__ = pow

if __name__ == '__main__':
  setup_variable()
  data = np.array(1.0)
  x = Variable(data)
  print(x.data)
  data = np.array([1, 2, 3])
  x.data = data
  print(x)
  print(getattr(Config, 'train'))
  with test_mode():
    print('train:', getattr(Config, 'train'))
  print('train:', getattr(Config, 'train'))

  a = Variable(np.array(1))
  b = Variable(np.array(2))
  result = a + b
  assert result.data == 3
  result.backward()
  print(a.grad)
  print(a)

  a = Variable(np.array([[1, 2, 3], [4, 5, 6]]))
  b = a.reshape((3, 2))
  print(a, b)