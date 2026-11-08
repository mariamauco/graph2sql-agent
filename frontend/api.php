<?php

declare(strict_types=1);

$agentUrl = rtrim((string) getenv('AGENT_URL'), '/');

// Compose supplies the private agent URL; the browser never connects to it directly.
$action = $_GET['action'] ?? '';
$routes = [
    'databases' => ['GET', '/api/databases'],
    'health' => ['GET', '/api/health'],
    'setup' => ['POST', '/api/setup'],
    'reset' => ['POST', '/api/reset'],
    'qa' => ['POST', '/api/agent/qa'],
    'edit' => ['POST', '/api/agent/edit'],
    'edit_accept' => ['POST', '/api/agent/edit/accept'],
];

if (!isset($routes[$action])) {
    http_response_code(404);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Unknown API action']);
    exit;
}

[$method, $path] = $routes[$action];

// Forward only the small API surface exposed by the frontend.
$headers = ['Content-Type: application/json'];
$options = [
    'http' => [
        'method' => $method,
        'header' => implode("\r\n", $headers),
        'ignore_errors' => true
    ],
];

if ($method === 'POST') {
    $options['http']['content'] = file_get_contents('php://input') ?: '{}';
}

$response = @file_get_contents($agentUrl . $path, false, stream_context_create($options));
$status = 502;
if (isset($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $matches)) {
    $status = (int) $matches[1];
}

http_response_code($status);
header('Content-Type: application/json');
echo $response !== false ? $response : json_encode([
    'error' => 'The agent service is unavailable',
    'hint' => 'Start the Docker Compose stack and try again.',
]);
