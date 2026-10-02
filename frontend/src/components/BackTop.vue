<template>
  <n-back-top :listen-to="listenTo" />
</template>

<script setup lang="ts">
import { NBackTop } from 'naive-ui'

/** App 外层 n-layout 的滚动容器。
 *  不能用 n-back-top 的自动探测：DOM 里有两层 .n-layout-scroll-container
 *  （外层真正滚动，n-layout-content 的内层永远不滚但离内容更近），探测会命中内层导致按钮永不出现 */
const listenTo = () =>
  document.querySelector<HTMLElement>('.n-layout--absolute-positioned > .n-layout-scroll-container') as HTMLElement
</script>
