@echo off
setlocal enabledelayedexpansion

:: ============================================
::  CONFIG -- apne values ke hisaab se change karo
:: ============================================
set FUNCTION_NAME=pricewatch-fetcher
set REGION=ap-southeast-2
set ALIAS_NAME=prod
set LAMBDA_DIR=lambda\pricewatch
set ZIP_PATH=lambda\pricewatch.zip

echo ===================================
echo  Step 1: Cleaning old zip
echo ===================================
if exist "%ZIP_PATH%" del "%ZIP_PATH%"

echo ===================================
echo  Step 2: Creating new zip from %LAMBDA_DIR%
echo ===================================
pushd "%LAMBDA_DIR%"
powershell -Command "Compress-Archive -Path * -DestinationPath ..\pricewatch.zip -Force"
popd

if not exist "%ZIP_PATH%" (
    echo ERROR: Zip file was not created. Aborting.
    exit /b 1
)

echo ===================================
echo  Step 3: Updating Lambda function code
echo ===================================
aws lambda update-function-code --function-name %FUNCTION_NAME% --zip-file fileb://%ZIP_PATH% --region %REGION%
if errorlevel 1 (
    echo ERROR: update-function-code failed. Aborting.
    exit /b 1
)

echo ===================================
echo  Step 4: Waiting for update to finish
echo ===================================
aws lambda wait function-updated --function-name %FUNCTION_NAME% --region %REGION%

echo ===================================
echo  Step 5: Publishing new version
echo ===================================
for /f "tokens=*" %%V in ('aws lambda publish-version --function-name %FUNCTION_NAME% --region %REGION% --query "Version" --output text') do set NEW_VERSION=%%V

if "%NEW_VERSION%"=="" (
    echo ERROR: Could not determine new version. Aborting.
    exit /b 1
)
echo New version published: %NEW_VERSION%

echo ===================================
echo  Step 6: Pointing alias "%ALIAS_NAME%" to version %NEW_VERSION%
echo ===================================
aws lambda update-alias --function-name %FUNCTION_NAME% --name %ALIAS_NAME% --function-version %NEW_VERSION% --region %REGION%
if errorlevel 1 (
    echo ERROR: update-alias failed. Aborting.
    exit /b 1
)

echo ===================================
echo  Step 7: Verifying with a test invoke (alias: %ALIAS_NAME%)
echo ===================================
aws lambda invoke --function-name %FUNCTION_NAME%:%ALIAS_NAME% --region %REGION% response_deploy_test.json
type response_deploy_test.json

echo.
echo ===================================
echo  DONE. Alias "%ALIAS_NAME%" now points to version %NEW_VERSION%
echo  EventBridge automatically uses this alias -- no need to touch the schedule.
echo ===================================

endlocal
