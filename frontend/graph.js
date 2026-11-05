// Render the graph returned by Flask using force-graph.
let graph;

function renderGraph(data) {
  const container = document.querySelector('#graph');
  const nodes = (data.nodes || []).map(node => node.data || node);
  const links = (data.edges || []).map(edge => edge.data || edge);
  if (graph && graph._destructor) graph._destructor();
  container.replaceChildren();

  // ForceGraph consumes plain nodes and links, while Flask keeps its graph API stable.
  graph = ForceGraph()(container)
    .graphData({nodes, links})
    .nodeId('id')
    .nodeLabel(node => `${node.label || node.id}`)
    .nodeColor(node => node.type === 'table' ? '#c85c35' : '#3d6fa3')
    .nodeRelSize(5)
    .linkLabel(link => link.label || link.type || '')
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(1)
    .linkColor(() => '#4f8f64')
    .width(container.clientWidth)
    .height(container.clientHeight);
}

window.addEventListener('resize', () => {
  if (!graph) return;
  const container = document.querySelector('#graph');
  graph.width(container.clientWidth).height(container.clientHeight);
});
