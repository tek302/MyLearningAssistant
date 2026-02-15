"""Script to visualize the RAG LangGraph by automatically extracting structure from the compiled graph."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graphs.rag_graph import get_rag_graph, create_rag_graph
from scripts.visualize_graph_common import visualize_graph as visualize_graph_common, extract_graph_structure_from_source


def visualize():
    """Visualize the RAG graph."""
    compiled_graph = get_rag_graph(reset=True)
    
    # Try to extract from compiled graph first
    from scripts.visualize_graph_common import extract_graph_structure
    structure = extract_graph_structure(compiled_graph)
    
    # If edges are missing, try source code parsing as fallback
    if not structure['edges'] and not structure['conditional_edges']:
        structure = extract_graph_structure_from_source(create_rag_graph)
        # Merge nodes from compiled graph
        compiled_nodes = [n for n in compiled_graph.nodes.keys() if not n.startswith('__') and not n.endswith(':edges')]
        structure['nodes'] = sorted(list(set(structure['nodes'] + compiled_nodes)))
    
    # Generate visualization
    from scripts.visualize_graph_common import generate_mermaid_diagram, generate_png
    import os
    
    mermaid_diagram = generate_mermaid_diagram(structure, "RAG")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "..", "rag_graph.mmd")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(mermaid_diagram)
    
    print("=" * 80)
    print("RAG LangGraph Visualization (Auto-extracted)")
    print("=" * 80)
    print()
    print("Extracting graph structure...")
    print(f"  Found {len(structure['nodes'])} nodes")
    print(f"  Found {len(structure['edges'])} simple edges")
    print(f"  Found {len(structure['conditional_edges'])} conditional edge sources")
    print()
    print("Generating Mermaid diagram...")
    print("-" * 80)
    print(mermaid_diagram)
    print()
    print(f"[OK] Saved to: {os.path.abspath(output_file)}")
    print()
    
    # Generate PNG
    print("PNG Generation:")
    print("-" * 80)
    png_file = os.path.join(script_dir, "..", "rag_graph.png")
    success = generate_png(mermaid_diagram, png_file)
    if success:
        print(f"[OK] PNG saved to: {os.path.abspath(png_file)}")
    else:
        print("[INFO] PNG generation skipped (mermaid-cli not available)")
        print("       To generate PNG, install: npm install -g @mermaid-js/mermaid-cli")
    print()
    print("=" * 80)
    print("Visualization complete!")
    print("=" * 80)


if __name__ == "__main__":
    visualize()
