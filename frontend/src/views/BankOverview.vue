<script setup>
// 屏幕：题库总览
// 职责：技术栈 → 知识点两级分组 + 背诵状态格 + 线性进度 + 圈选重点背诵
// 数据流（真实接口，失败回退 mock/bank.js 并 console.warn）：
//   GET  /api/bank/overview —— 分组 + 每题状态（done 掌握 / weak 薄弱·待补答 / todo 未背）
//   POST /api/bank/focus    —— 圈选/取消「重点背诵」分组（持久化到后端）
// 交互：点击分组头（.sub-head）切换 starred
// 动效：qcell hover 放大 + 悬停题目 tip（纯 CSS）
import { reactive, computed, onMounted } from 'vue'
import { bankOverview } from '../mock/bank'
import { getBankOverview, postBankFocus } from '../api'

// reactive 深拷贝，圈选状态可本地切换；真实数据到位后整体替换
const bank = reactive(JSON.parse(JSON.stringify(bankOverview)))

// mock 数据没有 stack key，按名字补一个（真实数据自带 key）
const NAME2KEY = { Python: 'python', Agent: 'agent', 'Vue 3': 'vue3' }

onMounted(async () => {
  try {
    const d = await getBankOverview()
    bank.done = d.done
    bank.total = d.total
    bank.stacks = d.stacks
  } catch (e) {
    console.warn('[bank] 获取题库总览失败，回退 mock 数据：', e.message)
  }
})

// 顶部线性进度：已背 / 总数
const pct = computed(() => (bank.total ? (bank.done / bank.total * 100).toFixed(0) : 0) + '%')

// 圈选/取消重点背诵分组：先本地切换，再持久化；失败回滚
async function toggleStar(stack, group) {
  group.starred = !group.starred
  try {
    await postBankFocus(stack.key || NAME2KEY[stack.name] || stack.name, group.name, group.starred)
  } catch (e) {
    group.starred = !group.starred
    console.warn('[bank] 圈选重点失败，已回滚：', e.message)
  }
}
</script>

<template>
  <section class="screen active">
    <div class="bank-wrap">
      <div class="iv-topbar" style="margin-bottom:14px">
        <span>QUESTION BANK — 题库总览</span>
        <span class="spacer"></span>
        <span>点击分组可圈选"重点背诵"</span>
      </div>
      <div class="bank-progress">
        <span class="mono" style="font-size:11px;letter-spacing:.12em;color:var(--ink-45)">已背诵</span>
        <div class="track"><i :style="{ width: pct }"></i></div>
        <span class="num">{{ bank.done }} / {{ bank.total }}</span>
      </div>

      <div class="bank-stack" v-for="stack in bank.stacks" :key="stack.name">
        <h3>{{ stack.name }} <span class="cnt">{{ stack.total }} 题 · 已背 {{ stack.done }}</span></h3>
        <div
          class="bank-sub"
          v-for="g in stack.groups"
          :key="g.name"
          :class="{ starred: g.starred }"
        >
          <div class="sub-head" @click="toggleStar(stack, g)">
            <span class="t">{{ g.name }}</span>
            <span class="mini">{{ g.cells.length }} 题</span>
            <span class="focus">{{ g.starred ? '重点背诵' : '+ 设为重点' }}</span>
          </div>
          <div class="cells">
            <div
              class="qcell"
              v-for="(c, ci) in g.cells"
              :key="c.question_id ?? ci"
              :class="{ done: c.status === 'done', weak: c.status === 'weak' }"
            ><span class="tip">{{ c.tip }}</span></div>
          </div>
        </div>
      </div>

      <div class="bank-legend">
        <span><i class="d"></i>已掌握</span>
        <span><i class="w"></i>薄弱 / 待补答</span>
        <span><i></i>未背诵</span>
        <span style="margin-left:auto">// 状态仅供你参考，Agent 抽题仍以真实表现为准</span>
      </div>
    </div>
  </section>
</template>
