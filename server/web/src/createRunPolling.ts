export type CreateRunPollingStatus = {
  status: 'running' | 'completed' | 'failed' | 'paused';
  message?: string | null;
};

type PollCreateRunOptions<T extends CreateRunPollingStatus> = {
  fetchStatus: () => Promise<T>;
  sleep: () => Promise<void>;
  onMessage: (message: string) => void;
};

export async function pollCreateRun<T extends CreateRunPollingStatus>(
  initialStatus: T,
  options: PollCreateRunOptions<T>,
): Promise<T> {
  let latest = initialStatus;
  while (latest.status === 'running') {
    await options.sleep();
    latest = await options.fetchStatus();
    if (latest.message) options.onMessage(latest.message);
  }
  return latest;
}
