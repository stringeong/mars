# M.A.R.S — Multi-Agent Resource Sharing (Frontend)

캡스톤 프로젝트 **M.A.R.S**의 웹 프론트엔드입니다. 자연어 프롬프트로 Multi-Agent 워크플로우를 생성하고,
로컬 기기와 클라우드 LLM을 조합해 실행/결과를 확인할 수 있는 대시보드형 앱입니다.

## 기술 스택

- **React 18 + TypeScript**
- **Vite** — 빌드/개발 서버
- **React Router v6** — 라우팅
- **@xyflow/react (React Flow v12)** — 워크플로우 캔버스(노드/엣지 편집)
- **Tailwind CSS** — 스타일링
- **lucide-react** — 아이콘

현재는 실제 백엔드 서버 없이 동작합니다.

- 워크플로우·실행·기기 데이터는 `src/data/mockData.ts`의 목업 데이터와 `src/context/DataContext.tsx`의
  인메모리 상태로 관리됩니다.
- 회원가입/로그인 계정 정보는 `src/context/AuthContext.tsx`에서 브라우저 `localStorage`
  (`mars_accounts` 키)에 저장됩니다. 실제 서비스로 전환할 때는 **비밀번호를 평문으로 저장하는 이 방식은
  반드시 백엔드 인증 API 호출로 교체**해야 합니다.

## 시작하기

```bash
npm install
npm run dev
```

`http://localhost:5173` 접속 후 `/signup`에서 계정을 새로 만들고 로그인하세요.
**회원가입한 이메일/비밀번호로만 로그인할 수 있습니다** — 임의의 값으로는 로그인되지 않습니다.

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
    workflow/        # MarsNode(커스텀 노드), DeletableEdge(삭제 가능한 커스텀 엣지),
                      # ComponentPalette, NodePropertiesPanel, ResourceStatusBar
    common/          # Card, StatusBadge, ProtectedRoute 등 공용 UI
  context/
    AuthContext.tsx  # 회원가입/로그인/프로필수정 — localStorage 기반 계정 저장소
    DataContext.tsx  # 워크플로우/기기/실행 인메모리 스토어 + 프롬프트→워크플로우 생성 로직
  data/
    mockData.ts      # 클라우드 모델, 워크플로우, 실행 이력, 이벤트 로그 목업
                      # (기기는 목업에 없고 사용자가 직접 등록해야 함 — 아래 참고)
  lib/
    security.ts      # 기기 보안 점수 계산 공식 (파일 접근 모드 + Agent 접근 범위 기반)
  pages/             # 아래 "페이지 매핑" 참고
  types/
    index.ts         # Device / Workflow / Execution 등 도메인 타입
```

## 페이지 매핑

| 라우트 | 페이지 | 설명 |
| --- | --- | --- |
| `/login` | `Login.tsx` | 로그인 — 가입된 이메일/비밀번호만 통과 |
| `/signup` | `Signup.tsx` | 회원가입 |
| `/` | `Dashboard.tsx` | 서비스(워크플로우) 목록, 통계 카드 |
| `/workflows/new` | `WorkflowCreate.tsx` | **① 서비스 생성 프롬프트 입력** — 자연어 설명 + 템플릿 + 기기/모델 선택 → Workflow 자동 생성 |
| `/workflows/:id` | `WorkflowBuilder.tsx` | **② 서비스(워크플로우) 수정** — 캔버스, 좌측 컴포넌트 팔레트(드래그앤드롭/블록코딩), 우측 노드 속성 패널(모델/시스템 프롬프트/온도/입출력 변수) |
| `/workflows/:id/run` | `WorkflowExecuteInput.tsx` | **③ 서비스 실행 프롬프트 입력** — Task Description, 파일 업로드, 개인 데이터 소스 선택, 예상 실행 리소스 |
| `/executions/:id` | `ExecutionResult.tsx` | **④ 결과 생성** — 미니 워크플로우 시각화, Agent Collaboration Summary, Final Output, 생성 파일, Agent Thinking Process(로그) |
| `/devices` | `Devices.tsx` | 기기 관리 — 신규 계정은 기기 0개로 시작(빈 상태 온보딩), 등록 드로어(폴더 접근, 파일 접근 모드, Agent 접근 범위) |
| `/executions` | `Executions.tsx` | 실행 이력 목록 (필터/검색) |
| `/data-sources` | `DataSources.tsx` | 개인 데이터 소스 연결 관리 |
| `/marketplace` | `Marketplace.tsx` | 워크플로우 템플릿 마켓플레이스 |
| `/events` | `EventLog.tsx` | 이벤트 로그(인증/기기/워크플로우/실행/보안/결제) |
| `/settings` | `Settings.tsx` | 프로필/보안/알림/요금제 설정 — 프로필 저장 시 계정 정보도 함께 갱신 |

## 워크플로우 빌더 사용법

- 좌측 **Components** 패널에서 Agent/Tool/Personal Data 블록을 캔버스로 드래그하거나 더블클릭하면 노드가 추가됩니다.
- 노드를 클릭하면 우측 **Node Properties** 패널이 열리고, 담당 기기·모델(Local LLM / Cloud LLM)·System Prompt·Temperature·Input/Output Variables를 편집할 수 있습니다.
- 노드의 핸들(점)을 드래그해 다른 노드와 연결하면 엣지(작업 흐름)가 생성됩니다.
- **연결선(엣지) 삭제**: 선 위에 마우스를 올리면 뜨는 × 버튼을 클릭하거나, 선을 선택한 뒤 `Delete`/`Backspace` 키를 누르면 삭제됩니다.
- **Save Draft**로 임시 저장, **Run Workflow**로 저장 후 실행 입력 화면(`/workflows/:id/run`)으로 이동합니다.

## 기기(Device) 보안 점수 기준

`src/lib/security.ts`에 정의되어 있으며, **기기 자체의 신뢰도가 아니라 그 기기에 부여한 접근 권한이
얼마나 제한적인지**로 계산됩니다.

| 요소 | 점수 |
| --- | --- |
| 파일 접근 — Read Only | +2 |
| 파일 접근 — Read + Write | +0 |
| Agent 범위 — Local Only | +2 |
| Agent 범위 — Selected Workflows | +1 |
| Agent 범위 — All Workflows | +0 |

합산 3~4점 → **High**, 1~2점 → **Medium**, 0점 → **Low**

새로 등록한 기기의 CPU/RAM 사용량은 0%가 아니라 낮은 유휴(idle) baseline 값으로 시작합니다 — 실제
컴퓨터는 완전히 아무것도 안 해도 OS 백그라운드 프로세스 때문에 항상 소량의 리소스를 사용하기 때문입니다.
이 게이지는 "M.A.R.S가 사용한 양"이 아니라 "그 기기의 현재 전체 시스템 사용량"을 나타냅니다.