# Windows PC 초기 설정 가이드

완전히 새로운 Windows PC에서 이 프로젝트를 실행하기 위해 필요한 설치 항목들입니다.

## 필수 설치 항목

### 1. Python 3.8 이상
- **다운로드**: https://www.python.org/downloads/
- **설치 시 주의사항**:
  - ✅ "Add Python to PATH" 체크박스 반드시 선택
  - ✅ "Install pip" 옵션 선택 (기본적으로 포함됨)
- **설치 확인**:
  ```bash
  python --version
  pip --version
  ```

### 2. Git (선택사항이지만 권장)
- **다운로드**: https://git-scm.com/download/win
- 버전 관리 및 프로젝트 클론에 사용
- 설치 확인:
  ```bash
  git --version
  ```

### 3. Visual C++ Build Tools (psycopg 설치 시 필요할 수 있음)
- **다운로드**: https://visualstudio.microsoft.com/visual-cpp-build-tools/
- 또는 **Visual Studio Community** 설치 시 C++ 개발 도구 포함
- `psycopg[binary]`를 사용하므로 대부분의 경우 필요 없지만, 문제 발생 시 설치

### 4. Android Studio 및 Android SDK (Android 개발 시 필요)
- **다운로드**: https://developer.android.com/studio
- **설치 시 주의사항**:
  - ✅ Android SDK, Android SDK Platform, Android Virtual Device (AVD) 포함 설치
  - ✅ 설치 후 Android Studio에서 SDK Manager 열어서 추가 구성 요소 설치
- **Java/JDK**:
  - Android Studio는 자체 JDK를 포함하므로 **별도 Java 설치 불필요**
  - Android Studio 내에서 JDK 경로 자동 설정됨
- **환경 변수 설정** (자동으로 설정됨):
  - `ANDROID_HOME`: `C:\Users\<사용자명>\AppData\Local\Android\Sdk`
  - `ANDROID_SDK_ROOT`: `C:\Users\<사용자명>\AppData\Local\Android\Sdk`
- **설치 확인**:
  ```bash
  # 새 터미널 창에서 확인 (환경 변수 새로고침 필요)
  echo $env:ANDROID_HOME
  adb version
  ```

## 선택적 설치 항목

### 5. Cursor (또는 VS Code)
- **다운로드**: https://cursor.sh/
- 코드 에디터 및 개발 환경

### 6. Windows Terminal (권장)
- Microsoft Store에서 설치 가능
- 더 나은 터미널 경험

## 설치 후 프로젝트 설정

1. **프로젝트 폴더로 이동**
   ```bash
   cd C:\path\to\TekLearningAgent\orchestrator
   ```

2. **가상환경 생성**
   ```bash
   python -m venv venv
   ```

3. **가상환경 활성화**
   ```bash
   venv\Scripts\activate
   ```

4. **Python 패키지 설치**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **환경 변수 설정**
   ```bash
   copy .env.example .env
   ```
   `.env` 파일을 열어서 실제 값 입력

## 설치 확인 체크리스트

- [ ] Python 3.8+ 설치됨 (`python --version`)
- [ ] pip 설치됨 (`pip --version`)
- [ ] 가상환경 생성됨
- [ ] requirements.txt의 모든 패키지 설치됨
- [ ] .env 파일 생성 및 설정 완료
- [ ] 서버 실행 가능 (`uvicorn app.main:app --reload`)

## 문제 해결

### psycopg 설치 오류 시
- `psycopg[binary]`를 사용 중이므로 대부분 문제 없음
- 오류 발생 시 Visual C++ Build Tools 설치

### pip 업그레이드 권장
```bash
python -m pip install --upgrade pip
```

### Android SDK를 찾을 수 없을 때

1. **환경 변수 확인**:
   ```powershell
   # 새 PowerShell 창에서 실행 (환경 변수 새로고침)
   echo $env:ANDROID_HOME
   echo $env:ANDROID_SDK_ROOT
   ```

2. **수동으로 환경 변수 설정** (필요한 경우):
   ```powershell
   # PowerShell을 관리자 권한으로 실행 후:
   [System.Environment]::SetEnvironmentVariable("ANDROID_HOME", "$env:LOCALAPPDATA\Android\Sdk", "User")
   [System.Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", "$env:LOCALAPPDATA\Android\Sdk", "User")
   ```
   설정 후 **새 터미널 창**을 열어야 적용됨

3. **Android Studio에서 SDK 경로 확인**:
   - Android Studio 실행
   - `File` → `Settings` (또는 `Ctrl + Alt + S`)
   - `Appearance & Behavior` → `System Settings` → `Android SDK`
   - `Android SDK Location` 확인

4. **Java/JDK 관련**:
   - Android Studio는 자체 JDK를 포함하므로 별도 설치 불필요
   - Android Studio에서 `File` → `Project Structure` → `SDK Location`에서 JDK 경로 확인 가능
   - 문제 발생 시: `File` → `Settings` → `Build, Execution, Deployment` → `Build Tools` → `Gradle`에서 JDK 경로 확인

5. **Gradle 빌드 오류 시**:
   - Android Studio에서 `File` → `Invalidate Caches / Restart` 실행
   - 프로젝트의 `local.properties` 파일에 SDK 경로 추가:
     ```properties
     sdk.dir=C\:\\Users\\<사용자명>\\AppData\\Local\\Android\\Sdk
     ```

