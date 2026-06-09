import { CONFIG, apiUrl } from '../config';

export async function fetchApi(
  endpointKey: keyof typeof CONFIG.api.endpoints | string,
  options?: RequestInit,
  dynamicParams?: string[]
): Promise<Response> {
  let endpoint = '';

  // Determine actual endpoint string
  if (Object.keys(CONFIG.api.endpoints).includes(endpointKey as string)) {
    endpoint = CONFIG.api.endpoints[endpointKey as keyof typeof CONFIG.api.endpoints];
    if (dynamicParams) {
       // if we have parameters, append them
       endpoint += '/' + dynamicParams.map(encodeURIComponent).join('/');
    }
  } else {
    // If it's a direct url
    endpoint = endpointKey as string;
  }

  const url = apiUrl(endpoint);

  const response = await fetch(url, options);
  if (!response.ok) {
    let errorDetail = `API returned ${response.status} ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData && errorData.detail) {
        errorDetail = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
      }
    } catch (e) {
      // Ignore JSON parse error, use default message
    }
    throw new Error(errorDetail);
  }
  return response;
}
