"""Alternative approach: Parse graph structure from source code."""

import ast
import inspect
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graphs.rag_graph import create_rag_graph

# Get the source code of create_rag_graph
source = inspect.getsource(create_rag_graph)
tree = ast.parse(source)

# Find all add_edge and add_conditional_edges calls
edges = []
conditional_edges = {}
nodes = set()
entry_point = None

for node in ast.walk(tree):
    # Find add_edge calls
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == 'add_edge':
            if len(node.args) >= 2:
                source = ast.literal_eval(node.args[0]) if isinstance(node.args[0], (ast.Str, ast.Constant)) else None
                target = ast.literal_eval(node.args[1]) if isinstance(node.args[1], (ast.Str, ast.Constant)) else None
                if source and target:
                    edges.append((source, target))
                    nodes.add(source)
                    nodes.add(target)
        
        # Find add_conditional_edges calls
        elif node.func.attr == 'add_conditional_edges':
            if len(node.args) >= 3:
                source = ast.literal_eval(node.args[0]) if isinstance(node.args[0], (ast.Str, ast.Constant)) else None
                if source and isinstance(node.args[2], ast.Dict):
                    conditions = {}
                    for k, v in zip(node.args[2].keys, node.args[2].values):
                        condition = ast.literal_eval(k) if isinstance(k, (ast.Str, ast.Constant)) else None
                        target = ast.literal_eval(v) if isinstance(v, (ast.Str, ast.Constant)) else None
                        if condition and target:
                            conditions[condition] = target
                            nodes.add(source)
                            nodes.add(target)
                    if conditions:
                        conditional_edges[source] = conditions
        
        # Find set_entry_point
        elif node.func.attr == 'set_entry_point':
            if len(node.args) >= 1:
                entry_point = ast.literal_eval(node.args[0]) if isinstance(node.args[0], (ast.Str, ast.Constant)) else None

print("Nodes:", sorted(nodes))
print("Edges:", edges)
print("Conditional edges:", conditional_edges)
print("Entry point:", entry_point)

