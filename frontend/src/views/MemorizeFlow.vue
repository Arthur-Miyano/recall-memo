<script setup>
// 屏幕：记忆训练流程（展示 → 考核 → 提示 → 即时反馈）
// 职责：阶段一展示题干+标准答案供记忆；阶段二打乱考核 + 评分 AGENT 即时反馈
// 数据流：mock/memorize.js → memorizeSession（未来 GET /api/memorize/session 等）
// 动效：
//   - 纸张掉落入场：.screen.active .paper 的 drop 动画（纯 CSS）
//   - mem-stage.quizzing 切换展示/考核两个区域（CSS 显隐 + screenIn）
//   - 关键词提示 kw-hint.show、反馈面板 quiz-feedback.show（drop 动画）
import { ref } from 'vue'
import { memorizeSession as m } from '../mock/memorize'

const quizzing = ref(false)   // 是否已进入考核阶段
const kwShow = ref(false)     // 关键词提示是否展开
const fbShow = ref(false)     // 即时反馈是否展示

// 开始考核：切到 quizzing 态（隐藏记忆展示，显示考核区）
function startQuiz() { quizzing.value = true }
// 提示（关键词）：反复点击开合
function toggleKw() { kwShow.value = !kwShow.value }
// 提交作答：展示评分 AGENT 即时反馈
function submitQuiz() { fbShow.value = true }
// 像素条：分数 → 10 格（向下取整，与原型静态格数一致）
function cells(v) { return Math.floor(v / 10) }
</script>

<template>
  <section class="screen active">
    <div class="mem-stage" id="mem-stage" :class="{ quizzing }">
      <div class="iv-topbar">
        <span>{{ m.topLeft }}</span>
        <span class="spacer"></span>
        <span>{{ m.topRight }}</span>
      </div>
      <div class="iv-line" style="margin-bottom:36px"><i style="width:100%"></i></div>

      <!-- 阶段一：展示题干+答案供记忆 -->
      <div class="mem-show">
        <div class="paper mem-q" v-for="q in m.questions" :key="q.no">
          <div class="paper-head">
            <span class="no">{{ q.no }}</span>
            <h3>{{ q.title }}</h3>
            <span class="retry-flag" v-if="q.retry">待补答</span>
          </div>
          <div class="answer"><span class="lbl">标准答案</span>{{ q.answer }}</div>
        </div>
        <div class="mem-actions">
          <button class="btn" @click="startQuiz">我记好了，开始考核 →</button>
          <span class="iv-note">// 考核时将打乱顺序，只显示变体题干</span>
        </div>
      </div>

      <!-- 阶段二：打乱考核 + 即时反馈 -->
      <div class="quiz-zone">
        <div class="iv-agent">面试官 AGENT 提问中</div>
        <h2 class="iv-question" style="font-size:clamp(22px,2.6vw,30px)">{{ m.quiz.question }}</h2>
        <div class="iv-follow"><span class="tag">{{ m.quiz.followTag }}</span></div>
        <div style="margin-bottom:16px">
          <button class="btn btn--ghost" style="padding:7px 20px;font-size:12px" @click="toggleKw">提示（关键词）</button>
          <div class="kw-hint" :class="{ show: kwShow }">
            <span class="tag" v-for="k in m.quiz.keywords" :key="k">{{ k }}</span>{{ ' ' }}
          </div>
        </div>
        <textarea class="iv-input" style="min-height:150px" :placeholder="m.quiz.placeholder"></textarea>
        <div class="iv-actions">
          <button class="btn" @click="submitQuiz">提交回答</button>
        </div>

        <!-- 即时反馈面板 -->
        <div class="paper quiz-feedback" :class="{ show: fbShow }">
          <div class="paper-head">
            <span class="no">{{ m.quiz.feedback.no }}</span>
            <h3>{{ m.quiz.feedback.title }}</h3>
            <span class="score">{{ m.quiz.feedback.score }}<small> /100</small></span>
          </div>
          <div class="dims">
            <div class="dim" v-for="d in m.quiz.feedback.dims" :key="d.label">
              {{ d.label }}<b :style="d.seal ? 'color:var(--seal)' : ''">{{ d.value }}</b>
              <div class="pixbar">
                <i v-for="i in 10" :key="i" :class="{ off: i > cells(d.value) }"></i>
              </div>
            </div>
          </div>
          <p class="comment">{{ m.quiz.feedback.comment }}</p>
          <div class="compare">
            <div><span class="lbl">你的回答</span>{{ m.quiz.feedback.yourAnswer }}</div>
            <div><span class="lbl">标准答案</span>{{ m.quiz.feedback.stdAnswer }}</div>
          </div>
          <div class="mem-actions">
            <button class="btn">下一题 →</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
