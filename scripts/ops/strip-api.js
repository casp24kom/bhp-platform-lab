function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // Only touch /api/* paths
  if (uri.startsWith('/api/')) {
    request.uri = uri.substring(4); // removes "/api"
    if (request.uri === '') request.uri = '/';
  } else if (uri === '/api') {
    request.uri = '/';
  }

  return request;
}