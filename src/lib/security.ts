import type { Device } from '@/types';

/**
 * Security score is derived purely from the access permissions granted to
 * M.A.R.S on a device — not from any property of the hardware itself. A
 * powerful, "trustworthy" NAS that is given read+write access for every
 * workflow scores lower than a phone that only grants read-only access to
 * its own local agents, because the *permission surface* is what an
 * attacker (or a buggy agent) could actually exploit.
 *
 * Scoring (2 factors, 0–4 points):
 *   File access mode   read-only        = +2   read+write = +0
 *   Agent access scope local-only       = +2
 *                       selected-workflows = +1
 *                       all-workflows    = +0
 *
 *   4–3 points → High     1–2 points → Medium     0 points → Low
 */
export function computeSecurityScore(
  fileAccessMode: Device['fileAccessMode'],
  agentAccessScope: Device['agentAccessScope']
): Device['securityScore'] {
  const filePoints = fileAccessMode === 'read-only' ? 2 : 0;
  const scopePoints = agentAccessScope === 'local-only' ? 2 : agentAccessScope === 'selected-workflows' ? 1 : 0;
  const total = filePoints + scopePoints;

  if (total >= 3) return 'High';
  if (total >= 1) return 'Medium';
  return 'Low';
}

export const SECURITY_SCORE_EXPLANATION =
  '보안 점수는 기기 자체의 신뢰도가 아니라, 이 기기에 부여한 접근 권한(파일 접근 모드 + Agent 접근 범위)이 얼마나 제한적인지로 계산됩니다. Read-only + Local Agents Only 조합이 가장 높은 점수를 받고, Read+Write + All Workflows 조합이 가장 낮은 점수를 받습니다.';
