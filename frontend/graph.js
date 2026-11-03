// Render the graph returned by Flask using Cytoscape.
let graph;

function renderGraph(data) {
  if (graph) graph.destroy();
  graph = cytoscape({
    container: document.querySelector('#graph'),
    elements: {nodes: data.nodes || [], edges: data.edges || []},
    style: [
      {selector: 'node[type="table"]', style: {
        'label': 'data(label)', 'background-color': '#c85c35',
        'color': '#17211b', 'text-valign': 'center'
      }},
      {selector: 'node[type="column"]', style: {
        'label': 'data(label)', 'background-color': '#87958b',
        'color': '#fffdf8', 'font-size': '9px', 'text-valign': 'center'
      }},
      {selector: 'edge', style: {
        'label': 'data(label)', 'curve-style': 'bezier',
        'target-arrow-shape': 'triangle', 'line-color': '#87958b',
        'target-arrow-color': '#87958b', 'font-size': '8px'
      }}
    ],
    layout: {name: 'cose', animate: false}
  });
}
