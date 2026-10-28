/** 제품 소개·워커 다운로드 페이지가 쓰는 배포 정보. 새 버전을 낼 때 RELEASE만 바꾼다. */

export const RELEASE = 'release0.0.3'
export const GITHUB_URL = 'https://github.com/stringeong/mars'

/** 워커 코드는 GitHub의 이 버전 압축 파일로 받는다. 풀면 `mars-<버전>` 폴더가 생긴다. */
export const DOWNLOADS = {
  zip: `${GITHUB_URL}/archive/refs/heads/${RELEASE}.zip`,
  tarball: `${GITHUB_URL}/archive/refs/heads/${RELEASE}.tar.gz`,
  folder: `mars-${RELEASE}`,
}

/** 워커가 접속할 서버 주소: 지금 보고 있는 웹 주소에 /api를 붙인 것 */
export function serverApiUrl() {
  return `${window.location.origin}/api`
}

export type Platform = 'windows' | 'mac' | 'linux'

/** 접속한 기기의 운영체제. 모르면 Windows로 본다. */
export function detectPlatform(): Platform {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  const value = `${nav.userAgentData?.platform ?? ''} ${navigator.platform ?? ''} ${navigator.userAgent}`.toLowerCase()
  if (value.includes('mac')) return 'mac'
  if (value.includes('linux') && !value.includes('android')) return 'linux'
  return 'windows'
}
