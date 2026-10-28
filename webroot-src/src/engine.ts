export interface EngineStatus { current: string; latest: string; staged: string; policy?: 'official' | 'bundled-compatibility' }

export function parseEngineStatus(text: string): EngineStatus {
  const data: unknown = JSON.parse(text);
  if (!data || typeof data !== 'object') throw new Error('引擎状态格式错误');
  const result = data as Record<string, unknown>;
  for (const key of ['current', 'latest', 'staged']) {
    if (typeof result[key] !== 'string' || !/^(?:\d{1,5}\.\d{1,5}\.\d{1,5})?$/.test(result[key])) {
      throw new Error('引擎版本格式错误');
    }
  }
  if (result.policy !== undefined && result.policy !== 'official' && result.policy !== 'bundled-compatibility') {
    throw new Error('引擎更新策略格式错误');
  }
  return result as unknown as EngineStatus;
}
