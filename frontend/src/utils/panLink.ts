/** 网盘分享链接识别（前端轻量版，与后端 pan/link.py 规则一致，用于索引前解析）。 */

const PLATFORMS: Record<string, RegExp> = {
  quark: /pan\.quark\.cn\/s\/([A-Za-z0-9]+)/i,
  uc: /drive\.uc\.cn\/s\/([A-Za-z0-9]+)/i,
  xunlei: /pan\.xunlei\.com\/s\/([A-Za-z0-9_-]+)/i,
  baidu: /pan\.baidu\.com\/s\/(1[A-Za-z0-9_-]+)/i,
  c139: /yun\.139\.com\/shareweb\/.*?\/w\/i\/([A-Za-z0-9_-]+)/i,
  pan123: /123(?:865|pan)\.(?:com|cn)\/s\/([A-Za-z0-9]+-[A-Za-z0-9]+)/i,
  pan115: /115(?:cdn|rc)?\.com\/s\/(sw[A-Za-z0-9]+)/i,
  guangya: /guangyapan\.com\/s\/([A-Za-z0-9_-]+)/i,
  ilanzou: /(?:^|[/.])ilanzou\.(?:com|net|org|cn)\/s\/([A-Za-z0-9_-]+)/i,
  lanzou: /(?:^|[/.])(?:lanzou[a-z0-9-]*|lan[zs]o[ux])\.(?:com|net|org|cn)\/([A-Za-z0-9]+)/i,
}

export interface ParsedShare {
  platform: string
  share_id: string
  passcode: string
}

export function parseShareLinkClient(text: string): ParsedShare | null {
  const urlMatch = (text || '').match(/https?:\/\/[^\s]+/)
  if (!urlMatch) return null
  const url = urlMatch[0].replace(/[。，,；;)\]}"']+$/, '')
  const pwdInUrl = url.match(/[?&](?:pwd|pass|passcode|password)=([A-Za-z0-9]+)/i)
  const pwdInText = text.match(/(?:提取码|访问码|密码)[：:]\s*([A-Za-z0-9]{4,8})/)
  const pwd = pwdInUrl?.[1] || pwdInText?.[1] || ''
  // ilanzou 先于 lanzou
  for (const key of ['quark', 'uc', 'xunlei', 'baidu', 'c139', 'pan123', 'pan115', 'guangya', 'ilanzou', 'lanzou']) {
    const m = url.match(PLATFORMS[key])
    if (m) {
      let sid = m[1]
      if (key === 'baidu') sid = sid.replace(/^1/, '')
      return { platform: key, share_id: sid, passcode: pwd }
    }
  }
  return null
}
