from modules.scraper import get_latest_bulletin

def run_test():
    print("========================================")
    print(" INICIANDO PRUEBA DEL SCRAPER (IGEPN)   ")
    print("========================================")
    
    # Usaremos el Reventador como volcán de prueba
    volcano_test = "Reventador"
    
    # Ejecutamos la función
    file_path, file_name = get_latest_bulletin(volcano_test)
    
    print("\n========================================")
    print(" RESULTADOS DE LA PRUEBA                ")
    print("========================================")
    
    if file_path and file_name:
        print("[+] Prueba Exitosa!")
        print(f"[+] Nombre del archivo: {file_name}")
        print(f"[+] Ruta completa: {file_path}")
    else:
        print("[-] La prueba falló. Revisa los errores en la consola.")
    print("========================================\n")

if __name__ == "__main__":
    run_test()
