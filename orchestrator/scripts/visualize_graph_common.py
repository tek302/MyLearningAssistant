"""Common utilities for visualizing LangGraph graphs."""

import sys
import os
import subprocess
import tempfile
from typing import Dict, Any, Callable

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def extract_graph_structure_from_source(create_graph_func):
    """
    Extract graph structure by parsing the source code of the graph creation function.
    This is a fallback when compiled graph introspection fails.
    """
    import ast
    import inspect
    from langgraph.graph import END
    
    try:
        source = inspect.getsource(create_graph_func)
        tree = ast.parse(source)
        
        edges = []
        conditional_edges = {}
        nodes = set()
        entry_point = None
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                # Find add_edge calls
                if node.func.attr == 'add_edge' and len(node.args) >= 2:
                    try:
                        source = ast.literal_eval(node.args[0]) if isinstance(node.args[0], (ast.Str, ast.Constant)) else None
                        target = ast.literal_eval(node.args[1]) if isinstance(node.args[1], (ast.Str, ast.Constant)) else None
                        if source and target:
                            edges.append((source, target))
                            nodes.add(source)
                            nodes.add(target)
                    except:
                        pass
                
                # Find add_conditional_edges calls
                elif node.func.attr == 'add_conditional_edges' and len(node.args) >= 3:
                    try:
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
                    except:
                        pass
                
                # Find set_entry_point
                elif node.func.attr == 'set_entry_point' and len(node.args) >= 1:
                    try:
                        entry_point = ast.literal_eval(node.args[0]) if isinstance(node.args[0], (ast.Str, ast.Constant)) else None
                    except:
                        pass
        
        # Convert edges list to dict format
        edges_dict = {}
        end_nodes = set()
        for source, target in edges:
            if target == END or str(target) == "__end__":
                end_nodes.add(source)
            else:
                if source not in edges_dict:
                    edges_dict[source] = []
                edges_dict[source].append(target)
        
        return {
            "nodes": sorted(list(nodes)),
            "edges": edges_dict,
            "conditional_edges": conditional_edges,
            "entry_point": entry_point,
            "end_nodes": end_nodes
        }
    except Exception as e:
        # If source parsing fails, return empty structure
        return {
            "nodes": [],
            "edges": {},
            "conditional_edges": {},
            "entry_point": None,
            "end_nodes": set()
        }


def extract_graph_structure(compiled_graph):
    """
    Extract graph structure from a compiled LangGraph object.
    
    Args:
        compiled_graph: Compiled LangGraph instance
        
    Returns:
        dict with 'nodes', 'edges', 'conditional_edges', 'entry_point', 'end_nodes'
    """
    from langgraph.graph import END
    
    # Get the internal graph object
    graph_obj = compiled_graph.get_graph()
    
    # Extract actual node names from compiled_graph.nodes
    # Filter out internal nodes like "__start__" and nodes ending with ":edges"
    all_node_keys = list(compiled_graph.nodes.keys()) if hasattr(compiled_graph, 'nodes') else []
    nodes = [n for n in all_node_keys if not n.startswith('__') and not n.endswith(':edges')]
    
    # Create mapping from hash IDs (from graph_obj.nodes) to actual node names
    # The key insight: compiled_graph.nodes has both node names and node_name:edges
    # graph_obj.nodes uses hash IDs, but we can map by comparing the node objects
    hash_to_name = {}
    name_to_hash = {}
    
    # Build mapping by comparing node objects
    if hasattr(graph_obj, 'nodes') and hasattr(compiled_graph, 'nodes'):
        graph_obj_nodes = graph_obj.nodes  # dict with hash IDs as keys
        compiled_nodes = compiled_graph.nodes  # dict with node names as keys
        
        # For each node name in compiled_graph.nodes, find its hash ID in graph_obj.nodes
        for node_name in nodes:
            if node_name in compiled_nodes:
                node_obj = compiled_nodes[node_name]
                node_obj_id = id(node_obj)
                
                # Try to find matching object in graph_obj.nodes
                for hash_id, hash_obj in graph_obj_nodes.items():
                    hash_obj_id = id(hash_obj)
                    # Use object identity (is) for exact match
                    if hash_obj is node_obj:
                        hash_to_name[hash_id] = node_name
                        name_to_hash[node_name] = hash_id
                        break
                    # Also try comparing by object ID
                    elif hash_obj_id == node_obj_id:
                        hash_to_name[hash_id] = node_name
                        name_to_hash[node_name] = hash_id
                        break
    
    # Extract entry point
    entry_point = None
    # Try to get from graph_obj.first_node (if available)
    if hasattr(graph_obj, 'first_node'):
        first_hash = graph_obj.first_node
        entry_point = hash_to_name.get(first_hash, None)
    elif hasattr(graph_obj, 'first'):
        first_hash = graph_obj.first
        entry_point = hash_to_name.get(first_hash, None)
    
    # Fallback: find entry point by name
    if not entry_point:
        for common_name in ["start_run", "fetch", "echo"]:
            if common_name in nodes:
                entry_point = common_name
                break
    
    # Extract edges and conditional edges
    edges = {}  # Simple edges: {source: [targets]}
    conditional_edges = {}  # Conditional edges: {source: {condition: target}}
    end_nodes = set()
    
    # Process edges from graph_obj
    if hasattr(graph_obj, 'edges'):
        edges_data = graph_obj.edges
        if isinstance(edges_data, list):
            for edge in edges_data:
                source_hash = getattr(edge, 'source', None)
                target_hash = getattr(edge, 'target', None)
                
                if source_hash is None or target_hash is None:
                    continue
                
                # Map hash IDs to node names
                source_name = hash_to_name.get(source_hash, None)
                if not source_name:
                    continue
                
                # Check if it's an END edge
                if target_hash == END:
                    end_nodes.add(source_name)
                else:
                    target_name = hash_to_name.get(target_hash, None)
                    if not target_name:
                        continue
                    
                    if source_name not in edges:
                        edges[source_name] = []
                    edges[source_name].append(target_name)
    
    # Extract conditional edges from node_name:edges entries
    # LangGraph stores conditional routing in compiled_graph.nodes with ":edges" suffix
    if hasattr(compiled_graph, 'nodes'):
        for key in compiled_graph.nodes.keys():
            if key.endswith(':edges') and key != '__start__:edges':
                source_name = key[:-6]  # Remove ':edges' suffix
                if source_name not in nodes:
                    continue
                
                edges_obj = compiled_graph.nodes[key]
                
                # Try to extract conditional routing from the edges object
                try:
                    # Check various possible attributes that might contain routing info
                    if hasattr(edges_obj, 'path'):
                        path = edges_obj.path
                        if isinstance(path, dict):
                            path_mapping = {}
                            for condition, target_hash in path.items():
                                target_name = hash_to_name.get(target_hash, None)
                                if target_name:
                                    path_mapping[condition] = target_name
                                elif target_hash == END:
                                    path_mapping[condition] = END
                            if path_mapping:
                                conditional_edges[source_name] = path_mapping
                    
                    # Also check for 'then' attribute
                    elif hasattr(edges_obj, 'then'):
                        then = edges_obj.then
                        if isinstance(then, dict):
                            path_mapping = {}
                            for condition, target_hash in then.items():
                                target_name = hash_to_name.get(target_hash, None)
                                if target_name:
                                    path_mapping[condition] = target_name
                                elif target_hash == END:
                                    path_mapping[condition] = END
                            if path_mapping:
                                conditional_edges[source_name] = path_mapping
                    
                    # Check if edges_obj itself is a dict (direct mapping)
                    elif isinstance(edges_obj, dict):
                        path_mapping = {}
                        for condition, target_hash in edges_obj.items():
                            target_name = hash_to_name.get(target_hash, None)
                            if target_name:
                                path_mapping[condition] = target_name
                            elif target_hash == END:
                                path_mapping[condition] = END
                        if path_mapping:
                            conditional_edges[source_name] = path_mapping
                except Exception:
                    pass
    
    # Also try compiled_graph.branches if available
    if hasattr(compiled_graph, 'branches'):
        try:
            branches = compiled_graph.branches
            if isinstance(branches, dict):
                for source_hash, branch_info in branches.items():
                    source_name = hash_to_name.get(source_hash, None)
                    if not source_name or source_name not in nodes:
                        continue
                    
                    # branch_info can be a dict mapping condition -> target
                    if isinstance(branch_info, dict):
                        path_mapping = {}
                        for condition, target_hash in branch_info.items():
                            if target_hash == END:
                                path_mapping[condition] = END
                            else:
                                target_name = hash_to_name.get(target_hash, None)
                                if target_name:
                                    path_mapping[condition] = target_name
                        
                        if path_mapping:
                            conditional_edges[source_name] = path_mapping
        except Exception:
            pass
    
    # If we couldn't find entry point, try to infer it
    if not entry_point and nodes:
        # Check which nodes have no incoming edges
        all_targets = set()
        for targets in edges.values():
            if isinstance(targets, list):
                for t in targets:
                    if t != END:
                        all_targets.add(t)
            else:
                if targets != END:
                    all_targets.add(targets)
        for cond_targets in conditional_edges.values():
            if isinstance(cond_targets, dict):
                for t in cond_targets.values():
                    if t != END:
                        all_targets.add(t)
        
        # Find nodes with no incoming edges
        nodes_with_no_incoming = set(nodes) - all_targets
        if nodes_with_no_incoming:
            # Use the first one (or common entry point names)
            for common_name in ["start_run", "fetch", "echo"]:
                if common_name in nodes_with_no_incoming:
                    entry_point = common_name
                    break
            if not entry_point:
                entry_point = list(nodes_with_no_incoming)[0]
        else:
            # Fallback to first node
            entry_point = nodes[0] if nodes else None
    
    return {
        "nodes": nodes,
        "edges": edges,
        "conditional_edges": conditional_edges,
        "entry_point": entry_point,
        "end_nodes": end_nodes
    }


def generate_mermaid_diagram(structure: Dict[str, Any], graph_name: str = "Graph") -> str:
    """
    Generate a Mermaid diagram from graph structure.
    
    Args:
        structure: Graph structure dict from extract_graph_structure()
        graph_name: Name of the graph for styling
        
    Returns:
        Mermaid diagram code as string
    """
    nodes = structure["nodes"]
    edges = structure["edges"]
    conditional_edges = structure["conditional_edges"]
    entry_point = structure["entry_point"]
    end_nodes = structure["end_nodes"]
    
    # Build Mermaid diagram with thicker edges
    mermaid_lines = [
        "graph TD",
        "    linkStyle default stroke-width:3px"
    ]
    
    # Add entry point
    if entry_point:
        mermaid_lines.append(f"    Start([{entry_point}])")
    
    # Process all edges
    processed_edges = set()
    
    # Process simple edges
    for source, targets in edges.items():
        if isinstance(targets, list):
            for target in targets:
                edge_key = (source, target)
                if edge_key not in processed_edges:
                    from langgraph.graph import END
                    if target == END or target in end_nodes or str(target) == "__end__":
                        mermaid_lines.append(f"    {source}[{source}] -->| | End([END])")
                    else:
                        mermaid_lines.append(f"    {source}[{source}] -->| | {target}[{target}]")
                    processed_edges.add(edge_key)
        else:
            # Single target
            target = targets
            edge_key = (source, target)
            if edge_key not in processed_edges:
                from langgraph.graph import END
                if target == END or target in end_nodes or str(target) == "__end__":
                    mermaid_lines.append(f"    {source}[{source}] -->| | End([END])")
                else:
                    mermaid_lines.append(f"    {source}[{source}] -->| | {target}[{target}]")
                processed_edges.add(edge_key)
    
    # Process conditional edges
    for source, conditions in conditional_edges.items():
        for condition, target in conditions.items():
            edge_key = (source, target, condition)
            if edge_key not in processed_edges:
                condition_label = condition.replace("_", " ").title()
                if target in end_nodes or target == "__end__":
                    mermaid_lines.append(f"    {source}[{source}] -->|{condition_label}| End([END])")
                else:
                    mermaid_lines.append(f"    {source}[{source}] -->|{condition_label}| {target}[{target}]")
                processed_edges.add(edge_key)
    
    # Add entry point edges
    if entry_point:
        if entry_point in edges:
            targets = edges[entry_point]
            if isinstance(targets, list):
                for target in targets:
                    from langgraph.graph import END
                    if target == END or target in end_nodes:
                        mermaid_lines.append(f"    Start -->| | End")
                    else:
                        mermaid_lines.append(f"    Start -->| | {target}[{target}]")
            else:
                from langgraph.graph import END
                if targets == END or targets in end_nodes:
                    mermaid_lines.append(f"    Start -->| | End")
                else:
                    mermaid_lines.append(f"    Start -->| | {targets}[{targets}]")
        if entry_point in conditional_edges:
            for condition, target in conditional_edges[entry_point].items():
                condition_label = condition.replace("_", " ").title()
                from langgraph.graph import END
                if target == END or target in end_nodes:
                    mermaid_lines.append(f"    Start -->|{condition_label}| End")
                else:
                    mermaid_lines.append(f"    Start -->|{condition_label}| {target}[{target}]")
    
    # Add styling based on node name patterns
    # LLM 호출 노드: 연한 분홍색 (#FFB6C1)
    # 나머지 노드: 연한 베이지색 (#FFF8DC)
    # 시작/종료: 연한 녹색 (#90EE90)
    mermaid_lines.extend([
        "",
        "    classDef startEnd fill:#90EE90,stroke:#333,stroke-width:2px",
        "    classDef llmNode fill:#FFB6C1,stroke:#333,stroke-width:2px",
        "    classDef defaultNode fill:#FFF8DC,stroke:#333,stroke-width:2px",
        "",
    ])
    
    # Auto-detect node types based on naming patterns
    # LLM 호출 노드: synthesize, judge, rewrite, retry_synthesize
    llm_nodes = [n for n in nodes if any(x in n.lower() for x in ["synthesize", "judge", "rewrite", "retry"])]
    start_end_nodes = []
    if entry_point:
        start_end_nodes.append("Start")
    start_end_nodes.append("End")
    
    # Apply styles
    if start_end_nodes:
        mermaid_lines.append(f"    class {','.join(start_end_nodes)} startEnd")
    
    if llm_nodes:
        mermaid_lines.append(f"    class {','.join(llm_nodes)} llmNode")
    
    # 나머지 모든 노드에 기본 스타일 적용
    default_nodes = [n for n in nodes if n not in llm_nodes]
    if default_nodes:
        mermaid_lines.append(f"    class {','.join(default_nodes)} defaultNode")
    
    return "\n".join(mermaid_lines)


def generate_png(mermaid_diagram: str, output_file: str) -> bool:
    """
    Generate PNG from Mermaid diagram using mermaid-cli or playwright.
    
    Args:
        mermaid_diagram: Mermaid diagram code
        output_file: Output PNG file path
        
    Returns:
        True if successful, False otherwise
    """
    # Method 1: Try using mermaid-cli (mmdc)
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False, encoding='utf-8') as tmp:
            tmp.write(mermaid_diagram)
            tmp_mmd = tmp.name
        
        try:
            # On Windows, prefer mmdc.cmd, otherwise try mmdc
            import shutil
            import platform
            import os as os_module
            
            mmdc_cmd = None
            if platform.system() == 'Windows':
                # Try multiple methods to find mmdc on Windows
                # Method 1: Use shutil.which
                mmdc_cmd = shutil.which('mmdc.cmd') or shutil.which('mmdc')
                
                # Method 2: Check common npm global paths
                if not mmdc_cmd:
                    appdata = os_module.getenv('APPDATA')
                    if appdata:
                        npm_paths = [
                            os_module.path.join(appdata, 'npm', 'mmdc.cmd'),
                            os_module.path.join(appdata, 'npm', 'mmdc'),
                        ]
                        for path in npm_paths:
                            if os_module.path.exists(path):
                                mmdc_cmd = path
                                break
                
                # Method 3: Check Program Files npm paths
                if not mmdc_cmd:
                    program_files = os_module.getenv('ProgramFiles')
                    if program_files:
                        npm_paths = [
                            os_module.path.join(program_files, 'nodejs', 'mmdc.cmd'),
                            os_module.path.join(program_files, 'nodejs', 'mmdc'),
                        ]
                        for path in npm_paths:
                            if os_module.path.exists(path):
                                mmdc_cmd = path
                                break
                
                # Method 4: Use 'where.exe' to find mmdc (Windows built-in)
                if not mmdc_cmd:
                    try:
                        where_result = subprocess.run(
                            ['where.exe', 'mmdc.cmd'],
                            capture_output=True,
                            timeout=5,
                            text=True
                        )
                        if where_result.returncode == 0 and where_result.stdout.strip():
                            mmdc_cmd = where_result.stdout.strip().split('\n')[0]
                    except:
                        pass
                
                # Method 5: Fallback to just 'mmdc.cmd' (might work if in PATH)
                if not mmdc_cmd:
                    mmdc_cmd = 'mmdc.cmd'
            else:
                mmdc_cmd = shutil.which('mmdc') or 'mmdc'
            
            # Prepare environment with current PATH to ensure node is found
            env = os_module.environ.copy()
            # Ensure nodejs directory is in PATH if it exists
            nodejs_paths = [
                os_module.path.join(os_module.getenv('ProgramFiles', ''), 'nodejs'),
                os_module.path.join(os_module.getenv('ProgramFiles(x86)', ''), 'nodejs'),
            ]
            current_path = env.get('PATH', '')
            for nodejs_path in nodejs_paths:
                if os_module.path.exists(nodejs_path) and nodejs_path not in current_path:
                    env['PATH'] = f"{nodejs_path};{current_path}"
            
            result = subprocess.run(
                [mmdc_cmd, '-i', tmp_mmd, '-o', output_file, '-b', 'white', '-w', '2400', '-H', '1800'],
                capture_output=True,
                timeout=30,
                check=False,
                text=True,
                shell=False,
                env=env
            )
            
            if result.returncode == 0:
                return True
            else:
                # Print error for debugging
                print(f"[DEBUG] mmdc failed with return code {result.returncode}")
                if result.stderr:
                    print(f"[DEBUG] stderr: {result.stderr[:500]}")
                if result.stdout:
                    print(f"[DEBUG] stdout: {result.stdout[:500]}")
        finally:
            try:
                os.unlink(tmp_mmd)
            except:
                pass
    except FileNotFoundError:
        print("[DEBUG] mmdc command not found in PATH")
    except subprocess.TimeoutExpired:
        print("[DEBUG] mmdc command timed out")
    except Exception as e:
        print(f"[DEBUG] mmdc error: {str(e)}")
    
    # Method 2: Try using Python with playwright (if available)
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
            </head>
            <body>
                <div class="mermaid">
{mermaid_diagram}
                </div>
                <script>
                    mermaid.initialize({{ startOnLoad: true }});
                </script>
            </body>
            </html>
            """
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp:
                tmp.write(html_content)
                tmp_html = tmp.name
            
            try:
                page.goto(f"file://{tmp_html}")
                page.wait_for_selector('.mermaid svg', timeout=10000)
                page.screenshot(path=output_file, full_page=True)
                browser.close()
                os.unlink(tmp_html)
                return True
            except Exception:
                browser.close()
                try:
                    os.unlink(tmp_html)
                except:
                    pass
                return False
    except ImportError:
        pass
    except Exception:
        pass
    
    return False


def visualize_graph(compiled_graph, graph_name: str, output_prefix: str = None):
    """
    Visualize a compiled LangGraph.
    
    Args:
        compiled_graph: Compiled LangGraph instance
        graph_name: Human-readable name for the graph
        output_prefix: Prefix for output files (defaults to graph_name.lower())
    """
    if output_prefix is None:
        output_prefix = graph_name.lower().replace(" ", "_")
    
    print("=" * 80)
    print(f"{graph_name} LangGraph Visualization (Auto-extracted)")
    print("=" * 80)
    print()
    
    # Extract structure
    print("Extracting graph structure...")
    structure = extract_graph_structure(compiled_graph)
    print(f"  Found {len(structure['nodes'])} nodes")
    print(f"  Found {len(structure['edges'])} simple edges")
    print(f"  Found {len(structure['conditional_edges'])} conditional edge sources")
    print()
    
    # Generate Mermaid diagram
    print("Generating Mermaid diagram...")
    print("-" * 80)
    mermaid_diagram = generate_mermaid_diagram(structure, graph_name)
    print(mermaid_diagram)
    print()
    
    # Save to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "..", f"{output_prefix}_graph.mmd")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(mermaid_diagram)
    print(f"[OK] Saved to: {os.path.abspath(output_file)}")
    print()
    
    print("To view the diagram:")
    print("  1. Go to https://mermaid.live")
    print("  2. Copy and paste the Mermaid code above")
    print("  3. Or open the saved .mmd file")
    print()
    
    # Print node summary
    print("Graph Summary:")
    print("-" * 80)
    nodes = structure["nodes"]
    print(f"Total nodes: {len(nodes)}")
    print(f"Nodes: {', '.join(sorted(nodes))}")
    print()
    
    # Try to generate PNG
    print("PNG Generation:")
    print("-" * 80)
    png_file = os.path.join(script_dir, "..", f"{output_prefix}_graph.png")
    print(f"Attempting to generate PNG: {os.path.abspath(png_file)}")
    success = generate_png(mermaid_diagram, png_file)
    if success:
        print(f"[OK] PNG saved to: {os.path.abspath(png_file)}")
    else:
        print("[WARN] PNG generation failed. Debug info above should show the reason.")
        print("       Common issues:")
        print("       - mmdc not in PATH (install: npm install -g @mermaid-js/mermaid-cli)")
        print("       - Puppeteer/Chromium not installed (run: mmdc --installPuppeteer)")
        print("       - File path issues")
        print(f"       You can manually generate PNG: mmdc -i {os.path.abspath(output_file)} -o {os.path.abspath(png_file)}")
    print()
    
    print("=" * 80)
    print("Visualization complete!")
    print("Note: This visualization is automatically extracted from the compiled graph.")
    print("      No manual updates needed when graph definition changes!")
    print("=" * 80)

