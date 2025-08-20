; GAN Cube Controller - AutoHotkey Bridge
; Listens to WebSocket messages and converts to real system input

#NoEnv
#SingleInstance Force
#Persistent

; WebSocket library (requires WebSocket.ahk)
; Download from: https://github.com/G33kDude/WebSocket.ahk

; Configuration
WS_PORT := 8081
MOUSE_SENSITIVITY := 2.0
KEY_REPEAT_RATE := 50  ; ms between repeated key presses

; State tracking
ActiveKeys := {}
LastMouseMove := A_TickCount

; Initialize WebSocket server
server := new WebSocket.Server("127.0.0.1", WS_PORT)
server.OnConnect := Func("OnConnect")
server.OnMessage := Func("OnMessage")
server.OnDisconnect := Func("OnDisconnect")

Gui, Add, Text,, GAN Cube Controller Bridge
Gui, Add, Text, w300 vStatus, Status: Waiting for connection on port %WS_PORT%
Gui, Add, Edit, w300 h100 vLog ReadOnly
Gui, Show,, GAN Cube Controller

LogMessage("AutoHotkey bridge started on port " . WS_PORT)
LogMessage("Waiting for browser connection...")

return

OnConnect(client) {
    GuiControl,, Status, Status: Connected to browser
    LogMessage("Browser connected!")
}

OnDisconnect(client) {
    GuiControl,, Status, Status: Disconnected - waiting for connection
    LogMessage("Browser disconnected")
    
    ; Release all active keys
    for key, _ in ActiveKeys {
        Send, {%key% up}
        ActiveKeys.Delete(key)
    }
}

OnMessage(client, message) {
    try {
        data := JSON.parse(message)
        
        if (data.type = "MOVE") {
            HandleCubeMove(data)
        } else if (data.type = "GYRO") {
            HandleOrientation(data)
        } else if (data.type = "KEY_PRESS") {
            HandleKeyPress(data)
        } else if (data.type = "KEY_RELEASE") {
            HandleKeyRelease(data)
        } else if (data.type = "MOUSE_CLICK") {
            HandleMouseClick(data)
        } else if (data.type = "MOUSE_MOVE") {
            HandleMouseMove(data)
        }
    } catch e {
        LogMessage("Error parsing message: " . e.message)
    }
}

HandleCubeMove(data) {
    move := data.move
    LogMessage("Cube move: " . move)
    
    ; Map cube moves to actions
    if (move = "R") {
        Click
        LogMessage("Sent: Left Click")
    } else if (move = "R'") {
        Click Right
        LogMessage("Sent: Right Click")
    } else if (move = "L") {
        Send, a
        LogMessage("Sent: Key A")
    } else if (move = "L'") {
        Send, d
        LogMessage("Sent: Key D")
    }
}

HandleKeyPress(data) {
    key := data.key
    if (!ActiveKeys[key]) {
        Send, {%key% down}
        ActiveKeys[key] := true
        LogMessage("Key pressed: " . key)
    }
}

HandleKeyRelease(data) {
    key := data.key
    if (ActiveKeys[key]) {
        Send, {%key% up}
        ActiveKeys.Delete(key)
        LogMessage("Key released: " . key)
    }
}

HandleMouseClick(data) {
    if (data.button = "left") {
        Click
        LogMessage("Mouse: Left Click")
    } else if (data.button = "right") {
        Click Right
        LogMessage("Mouse: Right Click")
    }
}

HandleMouseMove(data) {
    ; Limit mouse movement frequency
    if (A_TickCount - LastMouseMove < 16) ; ~60 FPS limit
        return
        
    deltaX := Round(data.deltaX * MOUSE_SENSITIVITY)
    deltaY := Round(data.deltaY * MOUSE_SENSITIVITY)
    
    if (deltaX != 0 || deltaY != 0) {
        MouseMove, %deltaX%, %deltaY%, 0, R
        LastMouseMove := A_TickCount
        LogMessage("Mouse moved: (" . deltaX . ", " . deltaY . ")")
    }
}

LogMessage(msg) {
    timestamp := A_Hour . ":" . A_Min . ":" . A_Sec
    logText := "[" . timestamp . "] " . msg . "`r`n"
    
    GuiControlGet, currentLog,, Log
    GuiControl,, Log, %currentLog%%logText%
    
    ; Scroll to bottom
    GuiControl, Focus, Log
    Send, ^{End}
}

GuiClose:
ExitApp

; JSON parsing library (simplified)
class JSON {
    static parse(str) {
        ; Simple JSON parser - you may want to use a full library
        ; This is a basic implementation for demonstration
        return {}
    }
}