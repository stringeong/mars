# M.A.R.S — Multi-Agent Resource Sharing (Frontend)

캡스톤 프로젝트 **M.A.R.S**의 웹 프론트엔드입니다. 자연어 프롬프트로 Multi-Agent 워크플로우를 생성하고,
로컬 기기와 클라우드 LLM을 조합해 실행/결과를 확인할 수 있는 대시보드형 앱입니다.

Figma 목업(`UI.pdf`)과 캡스톤 최종발표 자료를 기반으로 구현했습니다.

## 기술 스택

- **React 18 + TypeScript**
- **Vite** — 빌드/개발 서버
- **React Router v6** — 라우팅
- **ReactFlow (reactflow)** — 워크플로우 캔버스(노드/엣지 편집)
- **Tailwind CSS** — 스타일링
- **lucide-react** — 아이콘

현재는 백엔드 없이 동작하는 **프론트엔드 단독 데모**로, `src/data/mockData.ts`의 목업 데이터와
`src/context/DataContext.tsx`의 인메모리 상태로 모든 화면이 동작합니다. 실제 M.A.R.S 백엔드/에이전트 서버가
준비되면 `DataContext`, `AuthContext` 내부의 함수들을 실제 API 호출로 교체하면 됩니다.

## 시작하기

```bash
npm install
npm run dev
```

`http://localhost:5173` 접속 후, 로그인 화면에서 아무 이메일/비밀번호나 입력하면 목업 인증으로 로그인됩니다.

프로덕션 빌드:

```bash
npm run build
npm run preview
```

## 폴더 구조

```
src/
  components/
    layout/         # Sidebar, TopBar, AppLayout (앱 셸)
    workflow/        # MarsNode(ReactFlow 커스텀 노드), ComponentPalette,
                      # NodePropertiesPanel, ResourceStatusBar
    common/          # Card, StatusBadge, ProtectedRoute 등 공용 UI
  context/
    AuthContext.tsx  # 목업 로그인/로그아웃
    DataContext.tsx  # 워크플로우/실행 인메모리 스토어 + 프롬프트→워크플로우 생성 로직
  data/
    mockData.ts      # 기기, 클라우드 모델, 워크플로우, 실행 이력, 이벤트 로그 목업
  pages/             # 아래 "페이지 매핑" 참고
  types/
    index.ts         # Device / Workflow / Execution 등 도메인 타입
```

## 페이지 매핑 (요청하신 4개 핵심 화면 + 전체 화면)

| 라우트 | 페이지 | 설명 |
| --- | --- | --- |
| `/login` | `Login.tsx` | 로그인 |
| `/` | `Dashboard.tsx` | 서비스(워크플로우) 목록, 통계 카드 |
| `/workflows/new` | `WorkflowCreate.tsx` | **① 서비스 생성 프롬프트 입력** — 자연어 설명 + 템플릿 + 기기/모델 선택 → Workflow 자동 생성 |
| `/workflows/:id` | `WorkflowBuilder.tsx` | **② 서비스(워크플로우) 수정** — ReactFlow 캔버스, 좌측 컴포넌트 팔레트(드래그앤드롭), 우측 노드 속성 패널(모델/시스템 프롬프트/온도/입출력 변수) |
| `/workflows/:id/run` | `WorkflowExecuteInput.tsx` | **③ 서비스 실행 프롬프트 입력** — Task Description, 파일 업로드, 개인 데이터 소스 선택, 예상 실행 리소스 |
| `/executions/:id` | `ExecutionResult.tsx` | **④ 결과 생성** — 미니 워크플로우 시각화, Agent Collaboration Summary, Final Output, 생성 파일, Agent Thinking Process(로그) |
| `/devices` | `Devices.tsx` | 기기 관리 — 기기 카드(CPU/RAM 게이지), 기기 등록 드로어(폴더 접근, 파일 접근 모드, Agent 접근 범위) |
| `/executions` | `Executions.tsx` | 실행 이력 목록 (필터/검색) |
| `/data-sources` | `DataSources.tsx` | 개인 데이터 소스 연결 관리 |
| `/marketplace` | `Marketplace.tsx` | 워크플로우 템플릿 마켓플레이스 |
| `/events` | `EventLog.tsx` | 이벤트 로그(인증/기기/워크플로우/실행/보안/결제) |
| `/settings` | `Settings.tsx` | 프로필/보안/알림/요금제 설정 |

## 워크플로우 빌더(ReactFlow) 사용법

- 좌측 **Components** 패널에서 Agent/Tool/Personal Data 블록을 캔버스로 드래그하거나 더블클릭하면 노드가 추가됩니다.
- 노드를 클릭하면 우측 **Node Properties** 패널이 열리고, 담당 기기·모델(Local LLM / Cloud LLM)·System Prompt·Temperature·Input/Output Variables를 편집할 수 있습니다.
- 노드의 핸들(점)을 드래그해 다른 노드와 연결하면 엣지(작업 흐름)가 생성됩니다.
- **Save Draft**로 임시 저장, **Run Workflow**로 저장 후 실행 입력 화면(`/workflows/:id/run`)으로 이동합니다.

## 다음 단계 제안

1. `DataContext`의 `createWorkflowFromPrompt` / `runExecution`을 실제 M.A.R.S 백엔드(에이전트 오케스트레이션 API) 호출로 교체
2. `AuthContext`를 실제 인증(JWT 등)으로 교체
3. WebSocket 등으로 실행 중(`running`) 상태의 실시간 로그 스트리밍 연동
4. 기기 등록 드로어의 "Continue to Permissions" 이후 단계(디바이스 실제 페어링) 구현
