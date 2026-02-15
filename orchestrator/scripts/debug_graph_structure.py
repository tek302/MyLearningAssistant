"""Debug script to inspect LangGraph structure."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graphs.rag_graph import get_rag_graph

g = get_rag_graph(reset=True)

print("=" * 80)
print("Graph Structure Debug")
print("=" * 80)
print()

print("1. Compiled Graph Attributes:")
attrs = [x for x in dir(g) if not x.startswith('_')]
print(f"   Available attributes: {attrs[:30]}")
print()

print("2. Nodes:")
if hasattr(g, 'nodes'):
    nodes = g.nodes
    print(f"   Type: {type(nodes)}")
    print(f"   All keys: {list(nodes.keys())}")
    print(f"   Total: {len(nodes)}")
    if hasattr(nodes, 'items'):
        print(f"   First 3 items:")
        for i, (key, value) in enumerate(list(nodes.items())[:3]):
            print(f"      [{i}] {key}: {type(value)}")
print()

print("3. Graph Object:")
graph_obj = g.get_graph()
print(f"   Type: {type(graph_obj)}")
attrs = [x for x in dir(graph_obj) if not x.startswith('_')]
print(f"   Available attributes: {attrs[:30]}")
print()

print("4. Edges:")
if hasattr(graph_obj, 'edges'):
    edges = graph_obj.edges
    print(f"   Type: {type(edges)}")
    if isinstance(edges, list):
        print(f"   Total edges: {len(edges)}")
        if edges:
            print(f"   First 3 edges:")
            for i, e in enumerate(edges[:3]):
                print(f"      [{i}] {e}")
                print(f"         Type: {type(e)}")
                print(f"         Dir: {[x for x in dir(e) if not x.startswith('_')][:10]}")
                print(f"         source: {getattr(e, 'source', 'N/A')}")
                print(f"         target: {getattr(e, 'target', 'N/A')}")
    elif isinstance(edges, dict):
        print(f"   Edges dict keys: {list(edges.keys())[:10]}")
        if edges:
            first_key = list(edges.keys())[0]
            print(f"   First edge key: {first_key}")
            print(f"   First edge value: {edges[first_key]}")
print()

print("5. Branches (compiled_graph):")
if hasattr(g, 'branches'):
    branches = g.branches
    print(f"   Type: {type(branches)}")
    if isinstance(branches, dict):
        print(f"   Total branches: {len(branches)}")
        print(f"   Keys: {list(branches.keys())[:10]}")
        if branches:
            first_key = list(branches.keys())[0]
            first_val = branches[first_key]
            print(f"   First branch key: {first_key}")
            print(f"   First branch value type: {type(first_val)}")
            print(f"   First branch value: {first_val}")
            if isinstance(first_val, dict):
                print(f"   First branch value keys: {list(first_val.keys())}")
                print(f"   First branch value items: {list(first_val.items())}")
print()

print("6. Graph Object Branches:")
if hasattr(graph_obj, 'branches'):
    branches = graph_obj.branches
    print(f"   Type: {type(branches)}")
    if isinstance(branches, dict):
        print(f"   Total: {len(branches)}")
        print(f"   Keys: {list(branches.keys())[:10]}")
        if branches:
            first_key = list(branches.keys())[0]
            print(f"   First branch: {first_key} -> {branches[first_key]}")
print()

print("7. Try get_edges() if available:")
if hasattr(graph_obj, 'get_edges'):
    try:
        edges_result = graph_obj.get_edges()
        print(f"   get_edges() result type: {type(edges_result)}")
        print(f"   get_edges() result: {edges_result}")
    except Exception as e:
        print(f"   Error: {e}")
print()

print("8. Try to access graph structure directly:")
try:
    # Try to access internal structure
    if hasattr(graph_obj, 'nodes'):
        print(f"   graph_obj.nodes type: {type(graph_obj.nodes)}")
        if isinstance(graph_obj.nodes, dict):
            print(f"   graph_obj.nodes keys: {list(graph_obj.nodes.keys())[:5]}")
except Exception as e:
    print(f"   Error accessing nodes: {e}")

