// 测试环境引导：为 jsdom 提供完整可靠的 localStorage/sessionStorage。
// 某些 Node/jsdom 组合下 localStorage.clear 等 API 缺失或不可靠，
// 这里统一补一个内存实现，保证测试可复现。
class MemoryStorage {
  private store = new Map<string, string>()

  get length() { return this.store.size }
  clear() { this.store.clear() }
  getItem(key: string) { return this.store.has(key) ? this.store.get(key)! : null }
  setItem(key: string, value: string) { this.store.set(String(key), String(value)) }
  removeItem(key: string) { this.store.delete(key) }
  key(index: number) { return Array.from(this.store.keys())[index] ?? null }
}

function install(name: 'localStorage' | 'sessionStorage') {
  const existing = (globalThis as any)[name]
  if (existing && typeof existing.clear === 'function' && typeof existing.getItem === 'function') {
    return
  }
  Object.defineProperty(globalThis, name, {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  })
}

install('localStorage')
install('sessionStorage')
