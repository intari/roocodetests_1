function search_books(params, userSettings) {
  const query = params.query;
  const apiUrl = (userSettings.apiUrl || 'http://localhost:8000').replace(/\/$/, '');
  const useProxy = userSettings.useProxy || false;
  const proxyUrl = userSettings.proxyUrl || 'https://cors-anywhere.herokuapp.com/';
  
  // Debugging headers - WARNING: Only for development/testing
  const debugHeaders = userSettings.debugHeaders || {};
  
  if (!query) {
    throw new Error('Search query is required');
  }

  // Prepare the target URL
  const targetUrl = `${apiUrl}/search?query=${encodeURIComponent(query)}`;
  const requestUrl = useProxy ? `${proxyUrl}${targetUrl}` : targetUrl;

  // Add timeout handling
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  // Prepare headers
  const headers = {
    'Accept': 'application/json',
    ...(useProxy ? { 'X-Requested-With': 'XMLHttpRequest' } : {}),
    ...debugHeaders // Add debug headers if provided
  };

  return fetch(requestUrl, {
    method: 'GET',
    headers: headers,
    signal: controller.signal
  })
  .then(async response => {
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const errorBody = await response.text().catch(() => '');
      throw new Error(`API request failed with status ${response.status}. Response: ${errorBody}`);
    }
    
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      throw new Error(`Invalid content type: ${contentType}`);
    }
    
    return response.json();
  })
  .then(results => {
    if (!Array.isArray(results)) {
      throw new Error(`Invalid response format. Expected array, got ${typeof results}`);
    }

    if (results.length === 0) {
      return 'No books found matching your search';
    }

    // Format results with book paths and snippets
    return results.map(result => {
      if (!result.file_path || !result.snippet) {
        throw new Error('Invalid result format - missing required fields');
      }
      
      // Create properly encoded URL
      let formattedUrl = '';
      if (result.raw_url) {
        try {
          // Split URL into parts and encode components separately
          const url = new URL(result.raw_url);
          const pathParts = url.pathname.split('/').map(part =>
            encodeURIComponent(part).replace(/'/g, "%27")
          );
          const search = url.search ? '?' + encodeURIComponent(url.search.slice(1)) : '';
          formattedUrl = `${url.origin}${pathParts.join('/')}${search}`;
        } catch (e) {
          formattedUrl = result.raw_url; // Fallback to original if URL parsing fails
        }
      }
      
      return `Book: ${result.file_path}\n` +
             `Snippet: ${result.snippet}\n` +
             (formattedUrl ? `URL: ${formattedUrl}\n` : '');
    }).join('\n\n');
  })
  .catch(error => {
    clearTimeout(timeoutId);
    let errorMessage = `Error searching books: ${error.message}`;
    
    if (error.name === 'AbortError') {
      errorMessage += '\n\nDiagnostics: Request timed out. Check if:';
      errorMessage += `\n- The API is running at ${apiUrl}`;
      errorMessage += '\n- The server is accessible from your network';
      if (!useProxy) {
        errorMessage += '\n- Try enabling proxy in plugin settings';
      }
    } else if (error.message.includes('Failed to fetch') || error.message.includes('CORS')) {
      errorMessage += '\n\nDiagnostics: Network request failed. Check if:';
      errorMessage += `\n- The API URL (${apiUrl}) is correct`;
      errorMessage += '\n- CORS is properly configured on the server';
      errorMessage += '\n- The server is running and accessible';
      if (!useProxy) {
        errorMessage += '\n- Try enabling proxy in plugin settings to bypass CORS';
      }
      errorMessage += '\n- For debugging, you can add CORS headers in plugin settings';
    }
    
    return errorMessage;
  });
}