"""Test hash to name mapping."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graphs.rag_graph import get_rag_graph

g = get_rag_graph(reset=True)
go = g.get_graph()
cn = g.nodes
gn = go.nodes

print("Testing mapping...")
print(f"Compiled nodes (first 3): {list(cn.items())[:3]}")
print(f"Graph obj nodes (first 3): {list(gn.items())[:3]}")

# Try to find mapping
for name, obj in list(cn.items())[:3]:
    if not name.endswith(':edges') and not name.startswith('__'):
        print(f"\nNode: {name}")
        print(f"  Object: {obj}")
        print(f"  Object type: {type(obj)}")
        print(f"  Object id: {id(obj)}")
        
        # Try to find matching hash
        for hash_id, hash_obj in list(gn.items())[:3]:
            print(f"  Hash {hash_id}: id={id(hash_obj)}, match={obj is hash_obj}")

