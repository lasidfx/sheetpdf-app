# 악보 영상 → PDF (단일 실행 앱)

파이썬 설치 없이 `SheetPDF-windows.exe` / `SheetPDF-mac` 하나만 실행하면 브라우저에서 앱이 열립니다.

## 실행 파일 만드는 법 (GitHub, 무료·자동)
1. GitHub에서 새 저장소를 만들고 이 폴더 내용을 그대로 올립니다 (`.github` 폴더 포함).
2. 저장소 오른쪽 Releases → 최신 빌드에서 받습니다.

## 사용
링크 입력 → 영상 불러오기 → 악보 영역 조정 → 캡처 → 악기 선택 → PDF 만들고 정리하기.
저장 구조: `내 드라이브/악보/<악기>/<영상 제목>/` (PNG 낱장 + PDF)

- 드라이브 데스크톱 앱이 있으면 폴더를 자동으로 찾습니다.
- Drive API 방식: `credentials.json`(Google Cloud OAuth 데스크톱 클라이언트)을 실행 파일 옆에 두세요.
- 윈도우 첫 실행 시 SmartScreen 경고가 뜨면 ‘추가 정보 → 실행’.
