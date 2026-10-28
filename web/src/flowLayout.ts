/** 워크플로우 블록 자동 배치. 편집기와 제품 소개의 예시 캔버스가 같은 규칙을 쓴다. */

// 단계(열) 사이와 같은 단계 블록(행) 사이 간격
export const LAYOUT_COLUMN_GAP = 300
export const LAYOUT_ROW_GAP = 215

/** 단계별 블록 id 목록을 받아, 단계는 왼쪽→오른쪽으로 놓고 같은 단계(병렬) 블록은 세로로 쌓는다.
 *  각 열은 가장 높은 열에 맞춰 가운데 정렬한다. */
export function stagePositions(columns: string[][]): Record<string, { x: number; y: number }> {
  const tallest = Math.max(1, ...columns.map((column) => column.length))
  return Object.fromEntries(columns.flatMap((columnIds, column) => columnIds.map((id, row) => [id, {
    x: 60 + column * LAYOUT_COLUMN_GAP,
    y: 70 + ((tallest - columnIds.length) * LAYOUT_ROW_GAP) / 2 + row * LAYOUT_ROW_GAP,
  }])))
}
