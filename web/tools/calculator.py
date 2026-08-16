import ast
import operator as op
OPS={ast.Add:op.add,ast.Sub:op.sub,ast.Mult:op.mul,ast.Div:op.truediv,ast.Pow:op.pow,ast.USub:op.neg}
def calculate(expression):
 def run(node):
  if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):return node.value
  if isinstance(node,ast.BinOp) and type(node.op) in OPS:return OPS[type(node.op)](run(node.left),run(node.right))
  if isinstance(node,ast.UnaryOp) and type(node.op) in OPS:return OPS[type(node.op)](run(node.operand))
  raise ValueError("表达式只允许数字与 + - * / ** ()")
 return {"expression":expression,"result":run(ast.parse(expression,mode="eval").body)}
