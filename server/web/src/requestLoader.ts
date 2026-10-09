export function shareRequest<T>(
  inFlight: Map<string, Promise<T>>,
  key: string,
  request: () => Promise<T>,
): Promise<T> {
  const existing = inFlight.get(key);
  if (existing) return existing;
  const requestPromise = request();
  const shared = requestPromise.finally(() => {
    if (inFlight.get(key) === shared) inFlight.delete(key);
  });
  inFlight.set(key, shared);
  return shared;
}
