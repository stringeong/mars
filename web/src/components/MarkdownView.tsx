import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** 모델 출력(실행 결과·블록 출력)을 Markdown으로 보여준다.
 *  원본 HTML은 그리지 않고 글자로 둔다(react-markdown 기본값). 외부 이미지는 불러오지 않고 링크는 새 탭으로 연다. */
export default function MarkdownView({ text }: { text: string }) {
  return <div className="markdown-body">
    <Markdown
      remarkPlugins={[remarkGfm]}
      disallowedElements={['img']}
      unwrapDisallowed
      components={{ a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}
    >{text}</Markdown>
  </div>
}
