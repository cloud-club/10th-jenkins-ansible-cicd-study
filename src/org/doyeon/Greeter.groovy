package org.doyeon

class Greeter {
    String name

    Greeter(String name) {
        this.name = name
    }

    String greet() {
        return "안녕, ${name}! (from src/ class)"
    }
}
